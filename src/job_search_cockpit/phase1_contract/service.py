from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from job_search_cockpit.config import Settings
from job_search_cockpit.facts.review import (
    ManualContentReviewRequest,
    ReviewService,
    is_resume_eligible,
)
from job_search_cockpit.phase1_contract.retrieval import (
    RetrievalCandidate,
    classify_candidate,
    is_relevant_candidate,
    retrieve_matching_candidates,
)
from job_search_cockpit.phase1_contract.snapshots import (
    Phase1AcceptanceReceiptSnapshot,
    Phase1ActivationInputs,
    Phase1DisclosureAuthorizationRequest,
    Phase1DisclosureEpochRequest,
    Phase1DisclosureEpochSnapshot,
    Phase1DisclosureLifecycleRequest,
    Phase1DisclosureLifecycleSnapshot,
    Phase1DisclosurePayloadContext,
    Phase1FactDisclosureAuthorizationSnapshot,
    Phase1ManualContentReviewReceipt,
    Phase1ManualContentReviewRequest,
    Phase1MatchingFactSetSnapshot,
    Phase1MatchingFactSnapshot,
    Phase1MatchingManifestChoice,
    Phase1MatchingReleasedChoice,
    Phase1MatchingRelevanceEdge,
    Phase1MatchingRequirementQuery,
    Phase1MatchingRetrievalManifest,
    Phase1MatchingWordingRelease,
    Phase1ReadinessSnapshot,
    Phase1ResumeFactProjection,
    Phase1ResumeFactProjectionRequest,
    Phase1ResumeFactSnapshot,
    Phase1WordingReleaseRequest,
    SearchProfileSnapshot,
    canonical_fingerprint,
)
from job_search_cockpit.readiness.service import ReadinessService
from job_search_cockpit.search_profile.catalog import SearchProfilePayload
from job_search_cockpit.search_profile.service import get_active_profile
from job_search_cockpit.storage.database import session_factory_for
from job_search_cockpit.storage.models import (
    AuditEvent,
    Claim,
    ClaimRevision,
    ClaimSupportAssertion,
    ImportRun,
    ImportRunSource,
    Phase1AcceptanceReceipt,
    Phase1AuthorityState,
    Phase1FactDisclosureAuthorization,
    Phase1FactDisclosureAuthorizationFact,
    Phase1FactDisclosureAuthorizationTaxonomy,
    Phase1FactDisclosureLifecycleEvent,
    Phase1FactDisclosureReleaseEvent,
    Phase1MatchingDisclosureEpoch,
    Phase1MatchingRetrievalPreflight,
)
from job_search_cockpit.storage.mutation import MutationCoordinator
from job_search_cockpit.storage.recovery_ledger import RecoveryEvent


class Phase1ContractUnavailable(RuntimeError):
    """Raised when Phase I cannot safely authorize a later phase."""


@dataclass(frozen=True, slots=True)
class Phase1BuildMetadata:
    application_build: str
    acceptance_suite_version: str


class Phase1ContractService:
    def __init__(
        self, coordinator: MutationCoordinator, build_metadata: Phase1BuildMetadata
    ) -> None:
        self._coordinator = coordinator
        self._build_metadata = build_metadata

    @staticmethod
    def _schema_revision(session: Session) -> str:
        revision = session.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        return str(revision)

    @staticmethod
    def _receipt_snapshot(receipt: Phase1AcceptanceReceipt) -> Phase1AcceptanceReceiptSnapshot:
        return Phase1AcceptanceReceiptSnapshot(
            id=receipt.id,
            application_build=receipt.application_build,
            schema_revision=receipt.schema_revision,
            acceptance_suite_version=receipt.acceptance_suite_version,
            acceptance_run_id=receipt.acceptance_run_id,
            result_fingerprint=receipt.result_fingerprint,
            restore_high_water_mark=receipt.restore_high_water_mark,
            accepted_at=receipt.accepted_at.astimezone(UTC).isoformat(),
            fingerprint=receipt.fingerprint,
        )

    def record_acceptance(
        self,
        *,
        acceptance_run_id: str,
        result_fingerprint: str,
        actor: str,
        confirmation: str,
    ) -> Phase1AcceptanceReceiptSnapshot:
        if confirmation != "I ACCEPT THE PHASE I ACCEPTANCE RECEIPT":
            raise Phase1ContractUnavailable("The Phase I acceptance confirmation is required.")
        if not acceptance_run_id.strip() or len(result_fingerprint) != 64:
            raise Phase1ContractUnavailable("The Phase I acceptance receipt is incomplete.")

        def record(session: Session) -> Phase1AcceptanceReceiptSnapshot:
            authority = session.get(Phase1AuthorityState, 1)
            if authority is None:
                raise Phase1ContractUnavailable("The Phase I authority state is unavailable.")
            payload = {
                "application_build": self._build_metadata.application_build,
                "schema_revision": self._schema_revision(session),
                "acceptance_suite_version": self._build_metadata.acceptance_suite_version,
                "acceptance_run_id": acceptance_run_id.strip(),
                "result": "passed",
                "result_fingerprint": result_fingerprint,
                "restore_high_water_mark": authority.restore_generation,
                "actor": actor.strip(),
                "confirmation": confirmation,
            }
            receipt = Phase1AcceptanceReceipt(
                id=str(uuid4()),
                **payload,
                fingerprint=canonical_fingerprint(payload),
            )
            session.add(receipt)
            session.flush()
            return self._receipt_snapshot(receipt)

        return self._coordinator.run(record, "record_phase1_acceptance", expected_version=None)

    @staticmethod
    def _blocker_codes(report: object) -> tuple[str, ...]:
        fields = (
            ("latest_import_complete", "latest_import_incomplete"),
            ("active_profile_version", "active_profile_missing"),
            ("open_conflicts", "open_conflicts"),
            ("unresolved", "unresolved_facts"),
            ("sensitivity_unreviewed", "confidentiality_unreviewed"),
            ("stale", "stale_facts"),
            ("unsupported_approved", "unsupported_approved_facts"),
        )
        blockers: list[str] = []
        for attribute, code in fields:
            value = getattr(report, attribute)
            if attribute in {"latest_import_complete", "active_profile_version"}:
                if not value:
                    blockers.append(code)
            elif int(value) > 0:
                blockers.append(code)
        return tuple(blockers)

    def snapshot_activation_inputs(self) -> Phase1ActivationInputs:
        report = ReadinessService(self._coordinator).report()
        if not report.ready_for_phase_2:
            raise Phase1ContractUnavailable("Phase I is not ready for Phase II.")
        factory = session_factory_for(self._coordinator.engine)
        with factory() as session:
            receipt = session.scalar(
                select(Phase1AcceptanceReceipt).order_by(
                    Phase1AcceptanceReceipt.accepted_at.desc(), Phase1AcceptanceReceipt.id.desc()
                )
            )
            if receipt is None:
                raise Phase1ContractUnavailable("A durable Phase I acceptance receipt is required.")
            if (
                receipt.application_build != self._build_metadata.application_build
                or receipt.acceptance_suite_version
                != self._build_metadata.acceptance_suite_version
                or receipt.schema_revision != self._schema_revision(session)
            ):
                raise Phase1ContractUnavailable(
                    "A current acceptance receipt is required after a build or schema change."
                )
            authority = session.get(Phase1AuthorityState, 1)
            latest_import = session.scalar(
                select(ImportRun).order_by(ImportRun.committed_at.desc(), ImportRun.id.desc())
            )
            if authority is None or latest_import is None or not latest_import.complete:
                raise Phase1ContractUnavailable("The latest Phase I import is not complete.")
            source_rows = session.execute(
                select(ImportRunSource.source_key, ImportRunSource.content_hash).where(
                    ImportRunSource.import_run_id == latest_import.id,
                    ImportRunSource.status == "ready",
                )
            ).tuples()
            sources: dict[str, str | None] = {
                source_key: content_hash for source_key, content_hash in source_rows
            }
            source_keys = {source.key for source in Settings().sources}
            if set(sources) != source_keys or any(value is None for value in sources.values()):
                raise Phase1ContractUnavailable("The latest Phase I import is incomplete.")
            profile = get_active_profile(session)
            profile_payload = SearchProfilePayload.model_validate(profile.payload_json)
            source_hashes = dict(sorted((key, str(value)) for key, value in sources.items()))
            readiness_payload = {
                "ready_for_phase_2": report.ready_for_phase_2,
                "manifest_version": latest_import.manifest_version,
                "import_run_id": latest_import.id,
                "source_hashes": source_hashes,
                "active_profile_version": profile.version_number,
                "readiness_generation": authority.readiness_generation,
                "authority_high_water_mark": authority.authority_high_water_mark,
                "restore_generation": authority.restore_generation,
                "blocker_codes": self._blocker_codes(report),
            }
            readiness = Phase1ReadinessSnapshot(
                ready_for_phase_2=report.ready_for_phase_2,
                manifest_version=latest_import.manifest_version,
                import_run_id=latest_import.id,
                source_hashes=source_hashes,
                active_profile_version=profile.version_number,
                readiness_generation=authority.readiness_generation,
                authority_high_water_mark=authority.authority_high_water_mark,
                restore_generation=authority.restore_generation,
                blocker_codes=self._blocker_codes(report),
                fingerprint=canonical_fingerprint(readiness_payload),
            )
            profile_snapshot_payload = {
                "version_number": profile.version_number,
                "payload": profile_payload,
                "active_profile_generation": authority.active_profile_generation,
            }
            profile_snapshot = SearchProfileSnapshot(
                version_number=profile.version_number,
                payload=profile_payload,
                active_profile_generation=authority.active_profile_generation,
                fingerprint=canonical_fingerprint(profile_snapshot_payload),
            )
            return Phase1ActivationInputs(
                acceptance_receipt=self._receipt_snapshot(receipt),
                readiness=readiness,
                profile=profile_snapshot,
            )

    def snapshot_resume_fact_projection(
        self, request: Phase1ResumeFactProjectionRequest
    ) -> Phase1ResumeFactProjection:
        inputs = self.snapshot_activation_inputs()
        factory = session_factory_for(self._coordinator.engine)
        facts: list[Phase1ResumeFactSnapshot] = []
        with factory() as session:
            for requirement_id in request.requirement_ids:
                claim = session.scalar(
                    select(Claim).where(Claim.canonical_key == requirement_id)
                )
                if claim is None or claim.active_revision_id is None:
                    continue
                eligibility = is_resume_eligible(
                    session,
                    claim.id,
                    claim.active_revision_id,
                    named_use_id="",
                )
                if not eligibility.allowed:
                    continue
                revision = session.get(ClaimRevision, claim.active_revision_id)
                support = session.scalar(
                    select(ClaimSupportAssertion)
                    .where(
                        ClaimSupportAssertion.claim_id == claim.id,
                        ClaimSupportAssertion.revision_id == claim.active_revision_id,
                    )
                    .order_by(ClaimSupportAssertion.created_at.desc())
                )
                if revision is None or support is None or support.support_state != "supported":
                    continue
                facts.append(
                    Phase1ResumeFactSnapshot(
                        requirement_id=requirement_id,
                        claim_id=claim.id,
                        revision_id=revision.id,
                        support_assertion_id=support.id,
                        safe_wording=revision.display_value,
                        employer_key=revision.employer_key or None,
                        period_start=(
                            revision.period_start.isoformat()
                            if revision.period_start is not None
                            else None
                        ),
                        period_end=(
                            revision.period_end.isoformat()
                            if revision.period_end is not None
                            else None
                        ),
                    )
                )
        payload = {
            "requirement_ids": request.requirement_ids,
            "facts": [fact.model_dump(mode="json") for fact in facts],
            "profile_fingerprint": inputs.profile.fingerprint,
            "profile_generation": inputs.profile.active_profile_generation,
            "readiness_fingerprint": inputs.readiness.fingerprint,
            "readiness_generation": inputs.readiness.readiness_generation,
            "authority_fingerprint": inputs.acceptance_receipt.fingerprint,
            "authority_generation": inputs.readiness.authority_high_water_mark,
            "restore_generation": inputs.readiness.restore_generation,
        }
        return Phase1ResumeFactProjection(
            requirement_ids=request.requirement_ids,
            facts=tuple(facts),
            profile_fingerprint=inputs.profile.fingerprint,
            profile_generation=inputs.profile.active_profile_generation,
            readiness_fingerprint=inputs.readiness.fingerprint,
            readiness_generation=inputs.readiness.readiness_generation,
            authority_fingerprint=inputs.acceptance_receipt.fingerprint,
            authority_generation=inputs.readiness.authority_high_water_mark,
            restore_generation=inputs.readiness.restore_generation,
            fingerprint=canonical_fingerprint(payload),
        )

    def revalidate_resume_fact_projection(
        self, expected: Phase1ResumeFactProjection
    ) -> Phase1ResumeFactProjection:
        current = self.snapshot_resume_fact_projection(
            Phase1ResumeFactProjectionRequest(requirement_ids=expected.requirement_ids)
        )
        if current != expected:
            raise Phase1ContractUnavailable("The Phase I resume fact projection changed.")
        return current

    def snapshot_matching_fact_set(
        self, query: Phase1MatchingRequirementQuery
    ) -> Phase1MatchingFactSetSnapshot:
        projection = self.snapshot_resume_fact_projection(
            Phase1ResumeFactProjectionRequest(requirement_ids=query.requirement_ids)
        )
        facts = tuple(
            Phase1MatchingFactSnapshot(
                requirement_id=fact.requirement_id,
                claim_id=fact.claim_id,
                revision_id=fact.revision_id,
                support_assertion_id=fact.support_assertion_id,
            )
            for fact in projection.facts
        )
        payload = {
            "requirement_ids": query.requirement_ids,
            "facts": [fact.model_dump(mode="json") for fact in facts],
            "profile_fingerprint": projection.profile_fingerprint,
            "profile_generation": projection.profile_generation,
            "readiness_fingerprint": projection.readiness_fingerprint,
            "readiness_generation": projection.readiness_generation,
            "authority_fingerprint": projection.authority_fingerprint,
            "authority_generation": projection.authority_generation,
            "restore_generation": projection.restore_generation,
        }
        return Phase1MatchingFactSetSnapshot(
            requirement_ids=query.requirement_ids,
            facts=facts,
            profile_fingerprint=projection.profile_fingerprint,
            profile_generation=projection.profile_generation,
            readiness_fingerprint=projection.readiness_fingerprint,
            readiness_generation=projection.readiness_generation,
            authority_fingerprint=projection.authority_fingerprint,
            authority_generation=projection.authority_generation,
            restore_generation=projection.restore_generation,
            fingerprint=canonical_fingerprint(payload),
        )

    def revalidate_matching_fact_set(
        self, expected: Phase1MatchingFactSetSnapshot
    ) -> Phase1MatchingFactSetSnapshot:
        current = self.snapshot_matching_fact_set(
            Phase1MatchingRequirementQuery(requirement_ids=expected.requirement_ids)
        )
        if current != expected:
            raise Phase1ContractUnavailable("The Phase I matching fact set changed.")
        return current

    def snapshot_matching_retrieval_manifest(
        self, query: Phase1MatchingRequirementQuery
    ) -> Phase1MatchingRetrievalManifest:
        def snapshot(session: Session) -> Phase1MatchingRetrievalManifest:
            epoch = self._current_disclosure_epoch(session)
            authority = session.get(Phase1AuthorityState, 1)
            if authority is None:
                raise Phase1ContractUnavailable("The Phase I authority state is unavailable.")
            existing = session.scalar(
                select(Phase1MatchingRetrievalPreflight).where(
                    Phase1MatchingRetrievalPreflight.job_revision_id == query.job_revision_id,
                    Phase1MatchingRetrievalPreflight.coverage_ledger_fingerprint
                    == query.coverage_ledger_fingerprint,
                    Phase1MatchingRetrievalPreflight.disclosure_budget_epoch
                    == epoch.epoch_number,
                    Phase1MatchingRetrievalPreflight.phase1_authority_generation
                    == authority.authority_high_water_mark,
                )
            )
            query_fingerprint = canonical_fingerprint(query)
            if existing is not None:
                if existing.query_fingerprint != query_fingerprint:
                    raise Phase1ContractUnavailable(
                        "A changed query cannot reuse this matching preflight scope."
                    )
                return Phase1MatchingRetrievalManifest.model_validate(existing.manifest_json)

            manifest = self._snapshot_matching_retrieval_manifest(
                query,
                disclosure_budget_epoch=epoch.epoch_number,
                disclosure_policy_generation=epoch.policy_generation,
            )
            session.add(
                Phase1MatchingRetrievalPreflight(
                    id=str(uuid4()),
                    job_revision_id=query.job_revision_id,
                    coverage_ledger_fingerprint=query.coverage_ledger_fingerprint,
                    disclosure_budget_epoch=epoch.epoch_number,
                    phase1_authority_generation=manifest.authority_generation,
                    query_fingerprint=manifest.query_fingerprint,
                    manifest_fingerprint=manifest.fingerprint,
                    manifest_json=manifest.model_dump(mode="json"),
                )
            )
            session.flush()
            return manifest

        return self._coordinator.run_metadata(snapshot)

    @staticmethod
    def _current_disclosure_epoch(session: Session) -> Phase1MatchingDisclosureEpoch:
        epoch = session.scalar(
            select(Phase1MatchingDisclosureEpoch).order_by(
                Phase1MatchingDisclosureEpoch.epoch_number.desc()
            )
        )
        if epoch is None:
            raise Phase1ContractUnavailable("The matching disclosure epoch is unavailable.")
        return epoch

    def _snapshot_matching_retrieval_manifest(
        self,
        query: Phase1MatchingRequirementQuery,
        *,
        disclosure_budget_epoch: int,
        disclosure_policy_generation: int,
    ) -> Phase1MatchingRetrievalManifest:
        inputs = self.snapshot_activation_inputs()
        factory = session_factory_for(self._coordinator.engine)
        eligible: list[RetrievalCandidate] = []
        all_eligible_refs: list[dict[str, str]] = []
        ineligible_relevant = 0
        with factory() as session:
            claims = session.scalars(
                select(Claim)
                .where(Claim.active_revision_id.is_not(None))
                .order_by(Claim.canonical_key, Claim.id)
            )
            for claim in claims:
                if claim.active_revision_id is None:
                    continue
                revision = session.get(ClaimRevision, claim.active_revision_id)
                if revision is None:
                    continue
                support = session.scalar(
                    select(ClaimSupportAssertion)
                    .where(
                        ClaimSupportAssertion.claim_id == claim.id,
                        ClaimSupportAssertion.revision_id == revision.id,
                    )
                    .order_by(ClaimSupportAssertion.created_at.desc())
                )
                candidate = RetrievalCandidate(
                    canonical_key=claim.canonical_key,
                    claim_id=claim.id,
                    revision_id=revision.id,
                    support_assertion_id=support.id if support is not None else "",
                    category=claim.category,
                    subject=claim.subject,
                    safe_wording=revision.display_value,
                    employer_key=revision.employer_key or None,
                    period_start=(
                        revision.period_start.isoformat()
                        if revision.period_start is not None
                        else None
                    ),
                    period_end=(
                        revision.period_end.isoformat() if revision.period_end is not None else None
                    ),
                )
                classification = classify_candidate(candidate)
                relevant = is_relevant_candidate(query, candidate)
                if classification.known and not relevant:
                    continue
                eligibility = is_resume_eligible(
                    session,
                    claim.id,
                    revision.id,
                    named_use_id="",
                )
                if not eligibility.allowed:
                    if not classification.known:
                        continue
                    ineligible_relevant += 1
                    continue
                eligible.append(candidate)
                all_eligible_refs.append(
                    {
                        "canonical_key": candidate.canonical_key,
                        "claim_id": candidate.claim_id,
                        "revision_id": candidate.revision_id,
                        "support_assertion_id": candidate.support_assertion_id,
                        "safe_wording_sha256": sha256(
                            candidate.safe_wording.encode("utf-8")
                        ).hexdigest(),
                    }
                )

        result = retrieve_matching_candidates(query, tuple(eligible))
        omission_counts = dict(result.omission_reason_counts)
        if ineligible_relevant:
            omission_counts["ineligible_fact"] = ineligible_relevant
        choices = tuple(
            Phase1MatchingManifestChoice(
                claim_id=item.claim_id,
                revision_id=item.revision_id,
                support_assertion_id=item.support_assertion_id,
                safe_wording_sha256=sha256(item.safe_wording.encode("utf-8")).hexdigest(),
            )
            for item in result.choices
        )
        edges = tuple(
            Phase1MatchingRelevanceEdge(
                requirement_id=edge.requirement_id,
                claim_id=edge.claim_id,
                matched_taxonomy_ids=edge.matched_taxonomy_ids,
            )
            for edge in result.edges
        )
        query_fingerprint = canonical_fingerprint(query)
        eligible_set_fingerprint = canonical_fingerprint(all_eligible_refs)
        fields = {
            "query": query,
            "query_fingerprint": query_fingerprint,
            "retrieval_policy_version": "phase1.matching-retrieval.v1",
            "choices": choices,
            "edges": edges,
            "candidate_universe_count": result.candidate_universe_count,
            "examined_count": result.examined_count,
            "omission_reason_counts": tuple(sorted(omission_counts.items())),
            "complete": result.complete,
            "structural_state": "complete" if result.complete else "incomplete",
            "semantic_state": "complete" if result.complete else "unknown",
            "eligible_set_fingerprint": eligible_set_fingerprint,
            "profile_fingerprint": inputs.profile.fingerprint,
            "profile_generation": inputs.profile.active_profile_generation,
            "readiness_fingerprint": inputs.readiness.fingerprint,
            "readiness_generation": inputs.readiness.readiness_generation,
            "authority_fingerprint": inputs.acceptance_receipt.fingerprint,
            "authority_generation": inputs.readiness.authority_high_water_mark,
            "restore_generation": inputs.readiness.restore_generation,
            "disclosure_budget_epoch": disclosure_budget_epoch,
            "disclosure_policy_generation": disclosure_policy_generation,
        }
        return Phase1MatchingRetrievalManifest.model_validate(
            {**fields, "fingerprint": canonical_fingerprint(fields)}
        )

    def revalidate_matching_retrieval_manifest(
        self, expected: Phase1MatchingRetrievalManifest
    ) -> Phase1MatchingRetrievalManifest:
        with self._coordinator.consistent_read():
            current = self._snapshot_matching_retrieval_manifest(
                expected.query,
                disclosure_budget_epoch=expected.disclosure_budget_epoch,
                disclosure_policy_generation=expected.disclosure_policy_generation,
            )
        if current != expected:
            raise Phase1ContractUnavailable("The Phase I matching retrieval manifest changed.")
        return current

    @staticmethod
    def disclosure_payload_digest(
        manifest: Phase1MatchingRetrievalManifest,
        context: Phase1DisclosurePayloadContext,
    ) -> str:
        """Digest the exact logical payload shared with Phase II."""
        return canonical_fingerprint(
            {
                "digest_version": "phase1.matching-disclosure-digest.v1",
                "manifest": manifest,
                "context": context,
            }
        )

    @staticmethod
    def _authorization_state(
        session: Session, authorization: Phase1FactDisclosureAuthorization
    ) -> str:
        event = session.scalar(
            select(Phase1FactDisclosureLifecycleEvent)
            .where(
                Phase1FactDisclosureLifecycleEvent.authorization_id == authorization.id
            )
            .order_by(Phase1FactDisclosureLifecycleEvent.sequence.desc())
        )
        if event is None:
            raise Phase1ContractUnavailable("The disclosure lifecycle is unavailable.")
        return event.state

    @classmethod
    def _authorization_snapshot(
        cls, session: Session, authorization: Phase1FactDisclosureAuthorization
    ) -> Phase1FactDisclosureAuthorizationSnapshot:
        state = cls._authorization_state(session, authorization)
        expires_at = authorization.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        fields = {
            "authorization_id": authorization.id,
            "attempt_id": authorization.attempt_id,
            "nonce_sha256": authorization.nonce_sha256,
            "manifest_fingerprint": authorization.manifest_fingerprint,
            "logical_payload_digest": authorization.logical_payload_digest,
            "disclosure_budget_epoch": authorization.disclosure_budget_epoch,
            "disclosure_policy_generation": authorization.disclosure_policy_generation,
            "state": state,
            "expires_at": expires_at,
        }
        fingerprint_fields = {
            **fields,
            "expires_at": expires_at.isoformat(),
        }
        return Phase1FactDisclosureAuthorizationSnapshot.model_validate(
            {**fields, "fingerprint": canonical_fingerprint(fingerprint_fields)}
        )

    @staticmethod
    def _context_binding_error(
        manifest: Phase1MatchingRetrievalManifest,
        context: Phase1DisclosurePayloadContext,
    ) -> str:
        expected = (
            (context.manifest_fingerprint, manifest.fingerprint),
            (context.job_revision_id, manifest.query.job_revision_id),
            (
                context.coverage_ledger_fingerprint,
                manifest.query.coverage_ledger_fingerprint,
            ),
            (context.phase1_profile_generation, manifest.profile_generation),
            (context.phase1_readiness_generation, manifest.readiness_generation),
            (context.phase1_authority_generation, manifest.authority_generation),
            (context.phase1_restore_generation, manifest.restore_generation),
            (context.disclosure_budget_epoch, manifest.disclosure_budget_epoch),
            (
                context.disclosure_policy_generation,
                manifest.disclosure_policy_generation,
            ),
            (context.retrieval_configuration_version, manifest.retrieval_policy_version),
        )
        if any(actual != required for actual, required in expected):
            return "disclosure_context_mismatch"
        if not manifest.complete:
            return "retrieval_manifest_incomplete"
        return ""

    @staticmethod
    def _recovered_budget_identifiers(
        events: tuple[RecoveryEvent, ...], *, epoch: int, field: str
    ) -> set[str]:
        identifiers: set[str] = set()
        for event in events:
            if event.payload.get("epoch") != epoch:
                continue
            raw_identifiers = event.payload.get(field, ())
            if not isinstance(raw_identifiers, list) or any(
                not isinstance(identifier, str) for identifier in raw_identifiers
            ):
                raise Phase1ContractUnavailable("The disclosure recovery record is invalid.")
            identifiers.update(raw_identifiers)
        return identifiers

    def authorize_matching_disclosure(
        self, request: Phase1DisclosureAuthorizationRequest
    ) -> Phase1FactDisclosureAuthorizationSnapshot:
        denial_to_raise = ""

        def authorize(
            session: Session,
        ) -> tuple[Phase1FactDisclosureAuthorizationSnapshot, str]:
            stored_context = request.context.model_dump(mode="json")
            stored_context.pop("nonce")
            nonce_sha256 = sha256(request.context.nonce.encode("utf-8")).hexdigest()
            existing = session.scalar(
                select(Phase1FactDisclosureAuthorization).where(
                    Phase1FactDisclosureAuthorization.attempt_id
                    == request.context.attempt_id
                )
            )
            if existing is not None:
                if (
                    existing.logical_payload_digest != request.logical_payload_digest
                    or existing.context_json != stored_context
                    or existing.nonce_sha256 != nonce_sha256
                ):
                    raise Phase1ContractUnavailable(
                        "A disclosure attempt cannot be reused with a changed digest or context."
                    )
                snapshot = self._authorization_snapshot(session, existing)
                if snapshot.state != "authorized":
                    raise Phase1ContractUnavailable(
                        "A consuming or terminal disclosure attempt cannot be replayed."
                    )
                return snapshot, ""

            ledger_events = tuple(
                entry.event
                for entry in self._coordinator.recovery_ledger.read_all()
                if entry.event.event_type == "matching_disclosure_authorization"
            )
            ledger_attempts = {
                str(event.payload.get("attempt_id", "")) for event in ledger_events
            }
            if request.context.attempt_id in ledger_attempts:
                raise Phase1ContractUnavailable(
                    "The disclosure outcome is indeterminate and cannot be replayed."
                )

            preflight = session.scalar(
                select(Phase1MatchingRetrievalPreflight).where(
                    Phase1MatchingRetrievalPreflight.manifest_fingerprint
                    == request.context.manifest_fingerprint
                )
            )
            if preflight is None:
                raise Phase1ContractUnavailable("The authorized retrieval manifest is unavailable.")
            manifest = Phase1MatchingRetrievalManifest.model_validate(preflight.manifest_json)
            epoch = self._current_disclosure_epoch(session)
            if preflight.disclosure_budget_epoch != epoch.epoch_number:
                raise Phase1ContractUnavailable(
                    "A retrieval manifest from an earlier disclosure epoch cannot be authorized."
                )

            computed_digest = self.disclosure_payload_digest(manifest, request.context)
            reason_code = self._context_binding_error(manifest, request.context)
            if request.logical_payload_digest != computed_digest:
                reason_code = "logical_payload_digest_mismatch"
            now = datetime.now(UTC)
            expires_at = request.context.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            state = "authorized"
            if expires_at <= now:
                state = "expired"
                reason_code = "authorization_expired"
            elif reason_code:
                state = "denied"

            fact_ids = {choice.claim_id for choice in manifest.choices}
            taxonomy_ids = {
                taxonomy_id
                for requirement in manifest.query.requirements
                for taxonomy_id in requirement.taxonomy_ids()
            }
            prior_fact_ids = set(
                session.scalars(
                    select(Phase1FactDisclosureAuthorizationFact.claim_id)
                    .join(Phase1FactDisclosureAuthorization)
                    .where(
                        Phase1FactDisclosureAuthorization.disclosure_budget_epoch
                        == epoch.epoch_number
                    )
                )
            )
            prior_taxonomy_ids = set(
                session.scalars(
                    select(Phase1FactDisclosureAuthorizationTaxonomy.taxonomy_id)
                    .join(Phase1FactDisclosureAuthorization)
                    .where(
                        Phase1FactDisclosureAuthorization.disclosure_budget_epoch
                        == epoch.epoch_number
                    )
                )
            )
            recovered_fact_ids = self._recovered_budget_identifiers(
                ledger_events, epoch=epoch.epoch_number, field="fact_ids"
            )
            recovered_taxonomy_ids = self._recovered_budget_identifiers(
                ledger_events, epoch=epoch.epoch_number, field="taxonomy_ids"
            )
            if len(prior_fact_ids | recovered_fact_ids | fact_ids) > 64:
                state = "denied"
                reason_code = "disclosure_fact_budget_exhausted"
            if len(prior_taxonomy_ids | recovered_taxonomy_ids | taxonomy_ids) > 32:
                state = "denied"
                reason_code = "disclosure_taxonomy_budget_exhausted"

            authorization = Phase1FactDisclosureAuthorization(
                id=str(uuid4()),
                attempt_id=request.context.attempt_id,
                packet_id=request.context.packet_id,
                nonce_sha256=nonce_sha256,
                phase2_authorization_id=request.context.phase2_authorization_id,
                preflight_id=preflight.id,
                manifest_fingerprint=manifest.fingerprint,
                logical_payload_digest=request.logical_payload_digest,
                disclosure_budget_epoch=epoch.epoch_number,
                disclosure_policy_generation=epoch.policy_generation,
                context_json=stored_context,
                initial_state=state,
                reason_code=reason_code,
                issued_at=request.context.issued_at,
                expires_at=request.context.expires_at,
            )
            session.add(authorization)
            for claim_id in sorted(fact_ids):
                session.add(
                    Phase1FactDisclosureAuthorizationFact(
                        id=str(uuid4()), authorization_id=authorization.id, claim_id=claim_id
                    )
                )
            for taxonomy_id in sorted(taxonomy_ids):
                session.add(
                    Phase1FactDisclosureAuthorizationTaxonomy(
                        id=str(uuid4()),
                        authorization_id=authorization.id,
                        taxonomy_id=taxonomy_id,
                    )
                )
            lifecycle = Phase1FactDisclosureLifecycleEvent(
                id=str(uuid4()),
                authorization_id=authorization.id,
                logical_payload_digest=request.logical_payload_digest,
                sequence=1,
                state=state,
                reason_code=reason_code,
            )
            session.add(lifecycle)
            session.add(
                AuditEvent(
                    id=str(uuid4()),
                    event_type="matching_disclosure_authorized",
                    area="matching_disclosure",
                    subject_id=authorization.id,
                    summary=f"Matching disclosure authorization recorded as {state}.",
                    before_json=None,
                    after_json={
                        "manifest_fingerprint": manifest.fingerprint,
                        "logical_payload_digest": request.logical_payload_digest,
                        "attempt_id": request.context.attempt_id,
                        "epoch": epoch.epoch_number,
                        "state": state,
                        "reason_code": reason_code,
                        "fact_count": len(fact_ids),
                        "taxonomy_count": len(taxonomy_ids),
                    },
                    sensitive=False,
                    reason=reason_code,
                    source_label="Phase I matching disclosure",
                )
            )
            session.flush()
            self._coordinator.recovery_ledger.append(
                RecoveryEvent(
                    event_id=authorization.id,
                    event_type="matching_disclosure_authorization",
                    payload={
                        "authorization_id": authorization.id,
                        "attempt_id": request.context.attempt_id,
                        "manifest_fingerprint": manifest.fingerprint,
                        "logical_payload_digest": request.logical_payload_digest,
                        "epoch": epoch.epoch_number,
                        "state": state,
                        "reason_code": reason_code,
                        "fact_ids": sorted(fact_ids),
                        "taxonomy_ids": sorted(taxonomy_ids),
                    },
                    created_at=datetime.now(UTC),
                )
            )
            return self._authorization_snapshot(session, authorization), reason_code

        snapshot, denial_to_raise = self._coordinator.run_metadata(authorize)
        if snapshot.state == "denied":
            raise Phase1ContractUnavailable(
                f"The matching disclosure was denied: {denial_to_raise}."
            )
        return snapshot

    def record_disclosure_lifecycle(
        self, request: Phase1DisclosureLifecycleRequest
    ) -> Phase1DisclosureLifecycleSnapshot:
        def record(session: Session) -> tuple[Phase1DisclosureLifecycleSnapshot, bool]:
            authorization = session.get(
                Phase1FactDisclosureAuthorization, request.authorization_id
            )
            if authorization is None:
                raise Phase1ContractUnavailable("The disclosure authorization is unavailable.")
            if authorization.logical_payload_digest != request.logical_payload_digest:
                raise Phase1ContractUnavailable("The disclosure lifecycle digest changed.")
            current = self._authorization_state(session, authorization)
            terminals = {
                "validated_response",
                "expired",
                "denied",
                "failed",
                "indeterminate",
                "cancelled",
            }
            expires_at = authorization.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            expired_before_transition = (
                current not in terminals and expires_at <= datetime.now(UTC)
            )
            if expired_before_transition:
                next_state = "expired"
                reason_code = "authorization_expired_before_lifecycle"
            else:
                allowed = (
                    current == "authorized"
                    and request.state
                    in {"consuming", "expired", "denied", "failed", "indeterminate", "cancelled"}
                ) or (current == "consuming" and request.state in terminals)
                if not allowed:
                    raise Phase1ContractUnavailable(
                        "The disclosure lifecycle transition is terminal or invalid."
                    )
                next_state = request.state
                reason_code = request.reason_code
            sequence = session.scalar(
                select(Phase1FactDisclosureLifecycleEvent.sequence)
                .where(
                    Phase1FactDisclosureLifecycleEvent.authorization_id == authorization.id
                )
                .order_by(Phase1FactDisclosureLifecycleEvent.sequence.desc())
            )
            event = Phase1FactDisclosureLifecycleEvent(
                id=str(uuid4()),
                authorization_id=authorization.id,
                logical_payload_digest=request.logical_payload_digest,
                sequence=int(sequence or 0) + 1,
                state=next_state,
                reason_code=reason_code,
            )
            session.add(event)
            session.add(
                AuditEvent(
                    id=str(uuid4()),
                    event_type="matching_disclosure_lifecycle",
                    area="matching_disclosure",
                    subject_id=authorization.id,
                    summary=f"Matching disclosure moved from {current} to {next_state}.",
                    before_json={"state": current},
                    after_json={
                        "state": next_state,
                        "logical_payload_digest": request.logical_payload_digest,
                    },
                    sensitive=False,
                    reason=reason_code,
                    source_label="Phase I matching disclosure",
                )
            )
            session.flush()
            self._coordinator.recovery_ledger.append(
                RecoveryEvent(
                    event_id=event.id,
                    event_type="matching_disclosure_lifecycle",
                    payload={
                        "authorization_id": authorization.id,
                        "logical_payload_digest": request.logical_payload_digest,
                        "sequence": event.sequence,
                        "state": event.state,
                        "reason_code": event.reason_code,
                    },
                    created_at=datetime.now(UTC),
                )
            )
            fields = {
                "event_id": event.id,
                "authorization_id": event.authorization_id,
                "sequence": event.sequence,
                "state": event.state,
            }
            return (
                Phase1DisclosureLifecycleSnapshot.model_validate(
                    {**fields, "fingerprint": canonical_fingerprint(fields)}
                ),
                expired_before_transition,
            )

        snapshot, expired_before_transition = self._coordinator.run_metadata(record)
        if expired_before_transition:
            raise Phase1ContractUnavailable("The disclosure authorization expired.")
        return snapshot

    def release_matching_wording(
        self, request: Phase1WordingReleaseRequest
    ) -> Phase1MatchingWordingRelease:
        expected = request.authorization

        def release(
            session: Session,
        ) -> tuple[Phase1MatchingWordingRelease | None, str]:
            authorization = session.get(
                Phase1FactDisclosureAuthorization, expected.authorization_id
            )
            if authorization is None:
                raise Phase1ContractUnavailable("The disclosure authorization is unavailable.")
            nonce_sha256 = sha256(request.nonce.encode("utf-8")).hexdigest()
            if (
                request.attempt_id != authorization.attempt_id
                or expected.attempt_id != authorization.attempt_id
                or expected.nonce_sha256 != authorization.nonce_sha256
                or nonce_sha256 != authorization.nonce_sha256
            ):
                raise Phase1ContractUnavailable(
                    "The disclosure attempt or nonce binding is invalid."
                )
            current_snapshot = self._authorization_snapshot(session, authorization)
            if current_snapshot != expected:
                raise Phase1ContractUnavailable(
                    "The disclosure authorization changed or was replayed."
                )
            expires_at = authorization.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if current_snapshot.state == "expired":
                return None, "expired"
            if expires_at <= datetime.now(UTC):
                sequence = session.scalar(
                    select(Phase1FactDisclosureLifecycleEvent.sequence)
                    .where(
                        Phase1FactDisclosureLifecycleEvent.authorization_id
                        == authorization.id
                    )
                    .order_by(Phase1FactDisclosureLifecycleEvent.sequence.desc())
                )
                event = Phase1FactDisclosureLifecycleEvent(
                    id=str(uuid4()),
                    authorization_id=authorization.id,
                    logical_payload_digest=authorization.logical_payload_digest,
                    sequence=int(sequence or 0) + 1,
                    state="expired",
                    reason_code="authorization_expired_before_release",
                )
                session.add(event)
                session.add(
                    AuditEvent(
                        id=str(uuid4()),
                        event_type="matching_disclosure_lifecycle",
                        area="matching_disclosure",
                        subject_id=authorization.id,
                        summary="Matching disclosure expired before wording release.",
                        before_json={"state": "authorized"},
                        after_json={
                            "state": "expired",
                            "logical_payload_digest": authorization.logical_payload_digest,
                        },
                        sensitive=False,
                        reason="authorization_expired_before_release",
                        source_label="Phase I matching disclosure",
                    )
                )
                session.flush()
                self._coordinator.recovery_ledger.append(
                    RecoveryEvent(
                        event_id=event.id,
                        event_type="matching_disclosure_lifecycle",
                        payload={
                            "authorization_id": authorization.id,
                            "logical_payload_digest": authorization.logical_payload_digest,
                            "sequence": event.sequence,
                            "state": "expired",
                            "reason_code": "authorization_expired_before_release",
                        },
                        created_at=datetime.now(UTC),
                    )
                )
                return None, "expired"
            if current_snapshot.state != "authorized":
                raise Phase1ContractUnavailable(
                    "A consuming or terminal disclosure cannot be replayed."
                )
            preflight = session.get(
                Phase1MatchingRetrievalPreflight, authorization.preflight_id
            )
            if preflight is None:
                raise Phase1ContractUnavailable("The retrieval preflight is unavailable.")
            manifest = Phase1MatchingRetrievalManifest.model_validate(preflight.manifest_json)
            context = Phase1DisclosurePayloadContext.model_validate(
                {**authorization.context_json, "nonce": request.nonce}
            )
            if (
                self.disclosure_payload_digest(manifest, context)
                != authorization.logical_payload_digest
            ):
                raise Phase1ContractUnavailable("The disclosure digest is invalid.")
            current_manifest = self._snapshot_matching_retrieval_manifest(
                manifest.query,
                disclosure_budget_epoch=manifest.disclosure_budget_epoch,
                disclosure_policy_generation=manifest.disclosure_policy_generation,
            )
            if current_manifest != manifest:
                raise Phase1ContractUnavailable(
                    "The authorized matching facts changed before disclosure."
                )
            released: list[Phase1MatchingReleasedChoice] = []
            for choice in manifest.choices:
                claim = session.get(Claim, choice.claim_id)
                revision = session.get(ClaimRevision, choice.revision_id)
                support = session.get(ClaimSupportAssertion, choice.support_assertion_id)
                if (
                    claim is None
                    or revision is None
                    or support is None
                    or claim.active_revision_id != revision.id
                    or revision.claim_id != claim.id
                    or support.claim_id != claim.id
                    or support.revision_id != revision.id
                ):
                    raise Phase1ContractUnavailable(
                        "An authorized fact reference changed before disclosure."
                    )
                wording_hash = sha256(revision.display_value.encode("utf-8")).hexdigest()
                if wording_hash != choice.safe_wording_sha256:
                    raise Phase1ContractUnavailable(
                        "An authorized wording hash changed before disclosure."
                    )
                released.append(
                    Phase1MatchingReleasedChoice(
                        canonical_key=claim.canonical_key,
                        claim_id=claim.id,
                        revision_id=revision.id,
                        support_assertion_id=support.id,
                        safe_wording=revision.display_value,
                        safe_wording_sha256=wording_hash,
                    )
                )
            fields = {
                "authorization_id": authorization.id,
                "logical_payload_digest": authorization.logical_payload_digest,
                "manifest_fingerprint": manifest.fingerprint,
                "choices": tuple(released),
                "edges": manifest.edges,
            }
            wording_release = Phase1MatchingWordingRelease.model_validate(
                {**fields, "fingerprint": canonical_fingerprint(fields)}
            )
            sequence = session.scalar(
                select(Phase1FactDisclosureReleaseEvent.sequence)
                .where(
                    Phase1FactDisclosureReleaseEvent.authorization_id == authorization.id
                )
                .order_by(Phase1FactDisclosureReleaseEvent.sequence.desc())
            )
            release_event = Phase1FactDisclosureReleaseEvent(
                id=str(uuid4()),
                authorization_id=authorization.id,
                logical_payload_digest=authorization.logical_payload_digest,
                release_fingerprint=wording_release.fingerprint,
                sequence=int(sequence or 0) + 1,
            )
            session.add(release_event)
            session.add(
                AuditEvent(
                    id=str(uuid4()),
                    event_type="matching_wording_released",
                    area="matching_disclosure",
                    subject_id=authorization.id,
                    summary="Authorized matching wording was released.",
                    before_json=None,
                    after_json={
                        "logical_payload_digest": authorization.logical_payload_digest,
                        "release_fingerprint": wording_release.fingerprint,
                        "sequence": release_event.sequence,
                        "choice_count": len(released),
                    },
                    sensitive=False,
                    reason="authorized_local_manual_release",
                    source_label="Phase I matching disclosure",
                )
            )
            session.flush()
            self._coordinator.recovery_ledger.append(
                RecoveryEvent(
                    event_id=release_event.id,
                    event_type="matching_wording_released",
                    payload={
                        "authorization_id": authorization.id,
                        "logical_payload_digest": authorization.logical_payload_digest,
                        "release_fingerprint": wording_release.fingerprint,
                        "sequence": release_event.sequence,
                        "choice_count": len(released),
                    },
                    created_at=datetime.now(UTC),
                )
            )
            return wording_release, ""

        result, failure = self._coordinator.run_metadata(release)
        if result is None:
            raise Phase1ContractUnavailable(
                f"The disclosure authorization {failure}."
            )
        return result

    def start_new_matching_disclosure_epoch(
        self, request: Phase1DisclosureEpochRequest
    ) -> Phase1DisclosureEpochSnapshot:
        if request.confirmation != "START NEW MATCHING DISCLOSURE EPOCH":
            raise Phase1ContractUnavailable(
                "The exact matching disclosure epoch confirmation is required."
            )

        def start(session: Session) -> Phase1DisclosureEpochSnapshot:
            current = self._current_disclosure_epoch(session)
            epoch = Phase1MatchingDisclosureEpoch(
                id=str(uuid4()),
                epoch_number=current.epoch_number + 1,
                policy_generation=current.policy_generation + 1,
                reason=request.reason,
                confirmation=request.confirmation,
            )
            session.add(epoch)
            audit_id = str(uuid4())
            session.add(
                AuditEvent(
                    id=audit_id,
                    event_type="matching_disclosure_epoch_started",
                    area="matching_disclosure",
                    subject_id=epoch.id,
                    summary=f"Matching disclosure epoch {epoch.epoch_number} started.",
                    before_json={
                        "epoch": current.epoch_number,
                        "policy_generation": current.policy_generation,
                    },
                    after_json={
                        "epoch": epoch.epoch_number,
                        "policy_generation": epoch.policy_generation,
                    },
                    sensitive=False,
                    reason=request.reason,
                    source_label="Phase I matching disclosure",
                )
            )
            session.flush()
            self._coordinator.recovery_ledger.append(
                RecoveryEvent(
                    event_id=audit_id,
                    event_type="matching_disclosure_epoch_started",
                    payload={
                        "epoch_id": epoch.id,
                        "epoch": epoch.epoch_number,
                        "policy_generation": epoch.policy_generation,
                        "reason": request.reason,
                    },
                    created_at=datetime.now(UTC),
                )
            )
            fields = {
                "epoch_number": epoch.epoch_number,
                "policy_generation": epoch.policy_generation,
            }
            return Phase1DisclosureEpochSnapshot(
                **fields, fingerprint=canonical_fingerprint(fields)
            )

        return self._coordinator.run_metadata(start)

    def request_manual_content_review(
        self, request: Phase1ManualContentReviewRequest
    ) -> Phase1ManualContentReviewReceipt:
        self.snapshot_activation_inputs()
        receipt = ReviewService(self._coordinator).request_manual_content_review(
            ManualContentReviewRequest(
                canonical_key=request.canonical_key,
                category=request.category,
                safe_wording=request.safe_wording,
            )
        )
        if receipt.status.value != "unresolved" or receipt.origin != "user":
            raise Phase1ContractUnavailable("The manual content was not held for Phase I review.")
        return Phase1ManualContentReviewReceipt(
            claim_id=receipt.claim_id,
            revision_id=receipt.revision_id,
            status="unresolved",
            origin="user",
        )
