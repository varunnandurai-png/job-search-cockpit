from dataclasses import dataclass
from datetime import UTC
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
    Phase1ManualContentReviewReceipt,
    Phase1ManualContentReviewRequest,
    Phase1MatchingFactSetSnapshot,
    Phase1MatchingFactSnapshot,
    Phase1MatchingManifestChoice,
    Phase1MatchingRelevanceEdge,
    Phase1MatchingRequirementQuery,
    Phase1MatchingRetrievalManifest,
    Phase1ReadinessSnapshot,
    Phase1ResumeFactProjection,
    Phase1ResumeFactProjectionRequest,
    Phase1ResumeFactSnapshot,
    SearchProfileSnapshot,
    canonical_fingerprint,
)
from job_search_cockpit.readiness.service import ReadinessService
from job_search_cockpit.search_profile.catalog import SearchProfilePayload
from job_search_cockpit.search_profile.service import get_active_profile
from job_search_cockpit.storage.database import session_factory_for
from job_search_cockpit.storage.models import (
    Claim,
    ClaimRevision,
    ClaimSupportAssertion,
    ImportRun,
    ImportRunSource,
    Phase1AcceptanceReceipt,
    Phase1AuthorityState,
)
from job_search_cockpit.storage.mutation import MutationCoordinator


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
        with self._coordinator.consistent_read():
            return self._snapshot_matching_retrieval_manifest(query)

    def _snapshot_matching_retrieval_manifest(
        self, query: Phase1MatchingRequirementQuery
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
                canonical_key=item.canonical_key,
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
        }
        return Phase1MatchingRetrievalManifest.model_validate(
            {**fields, "fingerprint": canonical_fingerprint(fields)}
        )

    def revalidate_matching_retrieval_manifest(
        self, expected: Phase1MatchingRetrievalManifest
    ) -> Phase1MatchingRetrievalManifest:
        current = self.snapshot_matching_retrieval_manifest(expected.query)
        if current != expected:
            raise Phase1ContractUnavailable("The Phase I matching retrieval manifest changed.")
        return current

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
