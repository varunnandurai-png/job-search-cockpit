import sqlite3
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

import pytest
from sqlalchemy import inspect, select

from job_search_cockpit.phase1_contract.snapshots import (
    Phase1AcceptanceReceiptSnapshot,
    Phase1ActivationInputs,
    Phase1DisclosureLifecycleRequest,
    Phase1FactDisclosureAuthorizationSnapshot,
    Phase1MatchingFactResolutionRequest,
    Phase1MatchingManifestChoice,
    Phase1MatchingReleasedChoice,
    Phase1MatchingRelevanceEdge,
    Phase1MatchingRequirementQuery,
    Phase1MatchingRetrievalManifest,
    Phase1MatchingWordingRelease,
    Phase1ReadinessSnapshot,
    Phase1ResolvedMatchingFactSnapshot,
    SearchProfileSnapshot,
)
from job_search_cockpit.phase2.assessment_types import (
    EvidenceRelation,
    Requirement,
    ScoringComponent,
)
from job_search_cockpit.phase2.candidates import (
    CandidateWorkflowService,
    CandidateWorkflowUnavailable,
    LocalManualMappingLaunch,
    LocalManualMappingSelection,
    extract_public_requirements,
)
from job_search_cockpit.phase2.database import create_phase2_engine, upgrade_phase2_database
from job_search_cockpit.phase2.models import (
    Phase2DiscoveryRun,
    Phase2JobGateAssessment,
    Phase2JobRecord,
    Phase2JobRevision,
    Phase2LocalManualMappingAttempt,
    Phase2LocalManualMappingAttemptEvent,
    Phase2MatchAssessment,
    Phase2MatchComponent,
    Phase2RequirementMapping,
    Phase2SourceListingObservation,
)
from job_search_cockpit.phase2.mutation import Phase2InstanceLock, Phase2MutationCoordinator
from job_search_cockpit.phase2.types import Phase2ActivationView
from job_search_cockpit.search_profile.catalog import build_profile_v1

_NOW = datetime(2026, 8, 31, tzinfo=UTC)
_FENCE = {
    "phase1_profile_fingerprint": "a" * 64,
    "phase1_profile_generation": 1,
    "phase1_readiness_fingerprint": "b" * 64,
    "phase1_readiness_generation": 1,
    "phase1_authority_fingerprint": "c" * 64,
    "phase1_authority_generation": 1,
    "phase1_restore_generation": 0,
    "phase2_activation_generation": 1,
    "phase2_restore_generation": 0,
}


class _FaultInjectingPhase1:
    def __init__(
        self,
        manifest: Phase1MatchingRetrievalManifest,
        failure: Literal["before_consuming", "after_consuming", "none"] = "none",
        expire_on_terminal: bool = False,
        consuming_receipt_state: Literal["consuming", "expired"] = "consuming",
    ) -> None:
        self.manifest = manifest
        self.failure = failure
        self.expire_on_terminal = expire_on_terminal
        self.consuming_receipt_state = consuming_receipt_state
        self.state = "authorized"
        self.lifecycle: list[str] = []
        self.manifest_calls = 0

    def matching_retrieval_manifest(
        self, _query: Phase1MatchingRequirementQuery
    ) -> Phase1MatchingRetrievalManifest:
        self.manifest_calls += 1
        return self.manifest

    def revalidate_matching_retrieval_manifest(
        self, expected: Phase1MatchingRetrievalManifest
    ) -> Phase1MatchingRetrievalManifest:
        assert expected == self.manifest
        return expected

    def resolve_released_matching_facts(
        self, request: Phase1MatchingFactResolutionRequest
    ) -> tuple[Phase1ResolvedMatchingFactSnapshot, ...]:
        assert request.authorization.authorization_id == "phase1-auth-1"
        return tuple(
            Phase1ResolvedMatchingFactSnapshot(
                requirement_id=item.requirement_id,
                canonical_key="skills.product_management",
                claim_id=item.claim_id,
                revision_id=item.revision_id,
                support_assertion_id=item.support_assertion_id,
            )
            for item in request.facts
        )

    def record_disclosure_lifecycle(self, request: Phase1DisclosureLifecycleRequest) -> object:
        if request.state == "consuming":
            if self.failure == "before_consuming":
                raise RuntimeError("injected failure before Phase I consuming")
            assert self.state == "authorized"
            self.state = self.consuming_receipt_state
            self.lifecycle.append(self.consuming_receipt_state)
            if self.failure == "after_consuming":
                raise KeyboardInterrupt("injected interruption after Phase I consuming")
            return SimpleNamespace(state=self.consuming_receipt_state)
        if self.state not in {"authorized", "consuming"}:
            return SimpleNamespace(state=self.state)
        if self.expire_on_terminal:
            self.state = "expired"
            self.lifecycle.append("expired")
            return SimpleNamespace(state="expired")
        self.state = request.state
        self.lifecycle.append(request.state)
        return SimpleNamespace(state=request.state)


class _BeginningPhase1(_FaultInjectingPhase1):
    def __init__(
        self,
        manifest: Phase1MatchingRetrievalManifest,
        start_failure: Literal["authorization", "release"],
    ) -> None:
        super().__init__(manifest)
        self.start_failure = start_failure
        self.inputs = _phase1_inputs()

    def activation_inputs(self) -> Phase1ActivationInputs:
        return self.inputs

    def authorize_matching_disclosure(self, request: object) -> object:
        if self.start_failure == "authorization":
            raise RuntimeError("injected Phase I authorization failure")
        context = request.context  # type: ignore[union-attr]
        return Phase1FactDisclosureAuthorizationSnapshot(
            authorization_id=context.phase2_authorization_id,
            attempt_id=context.attempt_id,
            nonce_sha256="a" * 64,
            manifest_fingerprint=context.manifest_fingerprint,
            logical_payload_digest=request.logical_payload_digest,  # type: ignore[union-attr]
            disclosure_budget_epoch=1,
            disclosure_policy_generation=1,
            state="authorized",
            expires_at=context.expires_at,
            fingerprint="f" * 64,
        )

    def release_matching_wording(self, request: object) -> Phase1MatchingWordingRelease:
        if self.start_failure == "release":
            raise RuntimeError("injected Phase I release failure")
        raise AssertionError("the injected release failure must be raised")


class _WitnessAuthority:
    def persistence_fields(self) -> dict[str, str | int]:
        return _FENCE


class _FaultInjectingPublication:
    def __init__(
        self,
        coordinator: Phase2MutationCoordinator,
        *,
        interrupt_after_assessment: bool = False,
        fail_after_assessment: bool = False,
        insert_stale_revision: bool = False,
        corrupt_witness: bool = False,
        component_witness_corruption: Literal["none", "duplicate_name", "wrong_score"] = "none",
        none_mapping_identifiers: bool = False,
    ) -> None:
        self.coordinator = coordinator
        self.interrupt_after_assessment = interrupt_after_assessment
        self.fail_after_assessment = fail_after_assessment
        self.insert_stale_revision = insert_stale_revision
        self.corrupt_witness = corrupt_witness
        self.component_witness_corruption = component_witness_corruption
        self.none_mapping_identifiers = none_mapping_identifiers
        self.calls = 0
        self.expected_authority: object | None = None

    def publish(
        self,
        command: object,
        *,
        expected_manifest: object,
        expected_authority: object,
        publication_guard: object,
    ) -> str:
        del expected_manifest
        self.calls += 1
        self.expected_authority = expected_authority
        if self.insert_stale_revision:
            self._insert_newer_revision()

        def write(session: object) -> str:
            if not self.interrupt_after_assessment:
                publication_guard(session)  # type: ignore[operator]
            result = command.result  # type: ignore[union-attr]
            gate_id = f"gate-{result.assessment_id}"
            session.add(  # type: ignore[union-attr]
                Phase2JobGateAssessment(
                    id=gate_id,
                    job_revision_id=result.job_revision_id,
                    profile_fingerprint="a" * 64,
                    result="pass",
                    reason_codes_json=["profile_gate_pass"],
                )
            )
            session.add(  # type: ignore[union-attr]
                Phase2MatchAssessment(
                    id=result.assessment_id,
                    job_revision_id=result.job_revision_id,
                    job_gate_assessment_id=gate_id,
                    rubric_version="phase2-fixed-score.v1",
                    coverage_ledger_fingerprint=command.coverage_ledger_fingerprint,  # type: ignore[union-attr]
                    total_score=result.total_score,
                    qualified_band=result.qualified_band.value,
                    critical_floors_pass=result.critical_floors_pass,
                    meaningful_role_and_responsibility=result.meaningful_role_and_responsibility,
                    worthwhile_structure=result.worthwhile_structure,
                    unsupported_required=result.unsupported_required,
                    confidence=result.confidence.value,
                    assessment_state="stable",
                    fact_set_fingerprint=(
                        "e" * 64 if self.corrupt_witness else command.fact_set_fingerprint  # type: ignore[union-attr]
                    ),
                    **_FENCE,
                )
            )
            for component, score in (
                ("role", result.components.role),
                ("domain", result.components.domain),
                ("responsibility", result.components.responsibility),
                ("outcome", result.components.outcome),
                ("technical", result.components.technical),
                ("seniority", result.components.seniority),
                ("evidence", result.components.evidence),
            ):
                stored_component = (
                    "role"
                    if self.component_witness_corruption == "duplicate_name"
                    and component == "evidence"
                    else component
                )
                stored_score = (
                    score + 1
                    if self.component_witness_corruption == "wrong_score"
                    and component == "evidence"
                    else score
                )
                session.add(  # type: ignore[union-attr]
                    Phase2MatchComponent(
                        id=f"{result.assessment_id}-{component}",
                        match_assessment_id=result.assessment_id,
                        component=stored_component,
                        score=stored_score,
                        **_FENCE,
                    )
                )
            requirements = {item.requirement_id: item for item in command.requirements}  # type: ignore[union-attr]
            for mapping in command.mappings:  # type: ignore[union-attr]
                requirement = requirements[mapping.requirement_id]
                session.add(  # type: ignore[union-attr]
                    Phase2RequirementMapping(
                        id=f"{result.assessment_id}-{mapping.requirement_id}",
                        match_assessment_id=result.assessment_id,
                        requirement_id=requirement.requirement_id,
                        requirement_kind=requirement.kind.value,
                        component=requirement.component.value,
                        source_span_id=requirement.source_span_id,
                        source_start_offset=requirement.start_offset,
                        source_end_offset=requirement.end_offset,
                        claim_id=(
                            "claim-1"
                            if self.none_mapping_identifiers
                            and mapping.relation is EvidenceRelation.NONE
                            else mapping.claim_id
                        ),
                        fact_revision_id=(
                            "fact-revision-1"
                            if self.none_mapping_identifiers
                            and mapping.relation is EvidenceRelation.NONE
                            else mapping.revision_id
                        ),
                        support_assertion_id=(
                            "support-1"
                            if self.none_mapping_identifiers
                            and mapping.relation is EvidenceRelation.NONE
                            else mapping.support_assertion_id
                        ),
                        relation=mapping.relation.value,
                        reason_code=mapping.reason_code,
                        **_FENCE,
                    )
                )
            return result.assessment_id

        assessment_id = self.coordinator.run(write, "fault_injected_assessment")
        if self.interrupt_after_assessment:
            raise KeyboardInterrupt("injected interruption after Phase II assessment publication")
        if self.fail_after_assessment:
            raise RuntimeError("injected failure after Phase II assessment publication")
        return assessment_id

    def _insert_newer_revision(self) -> None:
        def write(session: object) -> None:
            session.add(  # type: ignore[union-attr]
                Phase2JobRevision(
                    id="revision-2",
                    job_record_id="job-1",
                    source_observation_id="observation-1",
                    canonical_url="https://jobs.example.test/1",
                    title="Product role",
                    employer_name="Example",
                    locations_json=["Hyderabad"],
                    posted_at=None,
                    public_description="Product role required.",
                    compensation_text=None,
                    content_fingerprint="f" * 64,
                    created_at=_NOW + timedelta(seconds=1),
                )
            )

        self.coordinator.run(write, "inject_stale_revision")


def _phase1_inputs() -> Phase1ActivationInputs:
    return Phase1ActivationInputs(
        acceptance_receipt=Phase1AcceptanceReceiptSnapshot(
            id="receipt-1",
            application_build="test-build",
            schema_revision="test",
            acceptance_suite_version="test",
            acceptance_run_id="run-1",
            result_fingerprint="r" * 64,
            restore_high_water_mark=0,
            accepted_at=_NOW.isoformat(),
            fingerprint="c" * 64,
        ),
        readiness=Phase1ReadinessSnapshot(
            ready_for_phase_2=True,
            manifest_version="test",
            import_run_id="import-1",
            source_hashes={"test": "s" * 64},
            active_profile_version=1,
            readiness_generation=1,
            authority_high_water_mark=1,
            restore_generation=0,
            fingerprint="b" * 64,
        ),
        profile=SearchProfileSnapshot(
            version_number=1,
            payload=build_profile_v1(),
            active_profile_generation=1,
            fingerprint="a" * 64,
        ),
    )


def _manifest(requirement: Requirement) -> Phase1MatchingRetrievalManifest:
    query = Phase1MatchingRequirementQuery(
        requirement_ids=(requirement.requirement_id,), job_revision_id="revision-1"
    )
    choice = Phase1MatchingManifestChoice(
        claim_id="claim-1",
        revision_id="fact-revision-1",
        support_assertion_id="support-1",
        safe_wording_sha256="f" * 64,
    )
    return Phase1MatchingRetrievalManifest(
        query=query,
        query_fingerprint="a" * 64,
        choices=(choice,),
        edges=(
            Phase1MatchingRelevanceEdge(
                requirement_id=requirement.requirement_id,
                claim_id=choice.claim_id,
                matched_taxonomy_ids=("role_profile.senior_product_manager",),
            ),
        ),
        candidate_universe_count=1,
        examined_count=1,
        omission_reason_counts=(),
        complete=True,
        structural_state="complete",
        semantic_state="complete",
        eligible_set_fingerprint="b" * 64,
        profile_fingerprint="a" * 64,
        profile_generation=1,
        readiness_fingerprint="b" * 64,
        readiness_generation=1,
        authority_fingerprint="c" * 64,
        authority_generation=1,
        restore_generation=0,
        disclosure_budget_epoch=1,
        disclosure_policy_generation=1,
        fingerprint="d" * 64,
    )


def _seed_candidate(
    coordinator: Phase2MutationCoordinator,
    *,
    description: str = "Product role required.",
    locations: list[str] | None = None,
) -> Phase2JobRevision:
    revision = Phase2JobRevision(
        id="revision-1",
        job_record_id="job-1",
        source_observation_id="observation-1",
        canonical_url="https://jobs.example.test/1",
        title="Product role",
        employer_name="Example",
        locations_json=locations or ["Hyderabad"],
        posted_at=None,
        public_description=description,
        compensation_text=None,
        content_fingerprint="e" * 64,
        created_at=_NOW,
    )

    def write_run(session: object) -> None:
        session.add(  # type: ignore[union-attr]
            Phase2DiscoveryRun(id="run-1", **_FENCE)
        )

    coordinator.run(write_run, "seed_candidate_recovery_run")

    def write_observation_and_job(session: object) -> None:
        session.add(  # type: ignore[union-attr]
            Phase2SourceListingObservation(
                id="observation-1",
                discovery_run_id="run-1",
                provider_id="test",
                provider_run_id=None,
                source_listing_id="listing-1",
                canonical_url=revision.canonical_url,
                title=revision.title,
                employer_name=revision.employer_name,
                locations_json=revision.locations_json,
                posted_at=None,
                public_description=revision.public_description,
                compensation_text=None,
                retrieved_at=_NOW,
                raw_content_fingerprint="f" * 64,
                content_fingerprint="e" * 64,
            )
        )
        session.add(Phase2JobRecord(id="job-1", posting_identity_fingerprint="d" * 64))  # type: ignore[union-attr]

    coordinator.run(write_observation_and_job, "seed_candidate_recovery_observation")

    def write_revision(session: object) -> None:
        session.add(revision)  # type: ignore[union-attr]

    coordinator.run(write_revision, "seed_candidate_recovery_revision")
    return revision


def _recovery_service(
    phase2_settings: object,
    *,
    phase1_failure: Literal["before_consuming", "after_consuming", "none"] = "none",
    phase1_expires_on_terminal: bool = False,
    phase1_consuming_receipt_state: Literal["consuming", "expired"] = "consuming",
    interrupt_after_assessment: bool = False,
    fail_after_assessment: bool = False,
    insert_stale_revision: bool = False,
    corrupt_witness: bool = False,
    component_witness_corruption: Literal["none", "duplicate_name", "wrong_score"] = "none",
    none_mapping_identifiers: bool = False,
    selection_relation: EvidenceRelation = EvidenceRelation.DIRECT,
    listing_locations: list[str] | None = None,
) -> tuple[
    CandidateWorkflowService,
    _FaultInjectingPhase1,
    _FaultInjectingPublication,
    LocalManualMappingLaunch,
    tuple[LocalManualMappingSelection, ...],
    Phase2MutationCoordinator,
    Phase2InstanceLock,
]:
    upgrade_phase2_database(f"sqlite:///{phase2_settings.database_path}")  # type: ignore[union-attr]
    engine = create_phase2_engine(phase2_settings)  # type: ignore[arg-type]
    lock = Phase2InstanceLock.acquire(phase2_settings)  # type: ignore[arg-type]
    coordinator = Phase2MutationCoordinator(phase2_settings, engine, lock)  # type: ignore[arg-type]
    revision = _seed_candidate(coordinator, locations=listing_locations)
    requirements = extract_public_requirements(revision)
    assert len(requirements) == 1
    manifest = _manifest(requirements[0])
    phase1 = _FaultInjectingPhase1(
        manifest,
        phase1_failure,
        expire_on_terminal=phase1_expires_on_terminal,
        consuming_receipt_state=phase1_consuming_receipt_state,
    )
    publication = _FaultInjectingPublication(
        coordinator,
        interrupt_after_assessment=interrupt_after_assessment,
        fail_after_assessment=fail_after_assessment,
        insert_stale_revision=insert_stale_revision,
        corrupt_witness=corrupt_witness,
        component_witness_corruption=component_witness_corruption,
        none_mapping_identifiers=none_mapping_identifiers,
    )
    service = CandidateWorkflowService(phase1, object(), coordinator, publication, now=lambda: _NOW)  # type: ignore[arg-type]
    launch = LocalManualMappingLaunch(
        attempt_id="attempt-1",
        nonce="nonce-1",
        job_revision_id=revision.id,
        selected_location_path="Hyderabad",
        requirements=requirements,
        choices=(),
        manifest_fingerprint=manifest.fingerprint,
        manifest=manifest,
        phase1_authorization_id="phase1-auth-1",
        phase1_authorization=Phase1FactDisclosureAuthorizationSnapshot(
            authorization_id="phase1-auth-1",
            attempt_id="attempt-1",
            nonce_sha256="a" * 64,
            manifest_fingerprint=manifest.fingerprint,
            logical_payload_digest="e" * 64,
            disclosure_budget_epoch=1,
            disclosure_policy_generation=1,
            state="authorized",
            expires_at=_NOW + timedelta(minutes=5),
            fingerprint="f" * 64,
        ),
        authority=_WitnessAuthority(),  # type: ignore[arg-type]
        logical_payload_digest="e" * 64,
        expires_at=_NOW + timedelta(minutes=5),
    )
    service._record_attempt(
        launch.attempt_id,
        launch.nonce,
        launch.phase1_authorization_id,
        launch.job_revision_id,
        launch.selected_location_path,
        "f" * 64,
        launch.manifest_fingerprint,
        launch.logical_payload_digest,
        launch.expires_at,
        _phase1_inputs(),
        Phase2ActivationView("active", "", 1, 0, 0, "receipt-1", 1),
    )
    if selection_relation is EvidenceRelation.NONE:
        selections = (
            LocalManualMappingSelection(
                requirement_id=requirements[0].requirement_id,
                relation=EvidenceRelation.NONE,
                reason_code="none/no_approved_evidence_found",
            ),
        )
    else:
        selections = (
            LocalManualMappingSelection(
                requirement_id=requirements[0].requirement_id,
                relation=EvidenceRelation.DIRECT,
                reason_code="direct/exact_capability_performed",
                claim_id="claim-1",
                revision_id="fact-revision-1",
                support_assertion_id="support-1",
            ),
        )
    return service, phase1, publication, launch, selections, coordinator, lock


def _attempt_state(coordinator: Phase2MutationCoordinator) -> str:
    with coordinator._session_factory() as session:
        attempt = session.scalar(
            select(Phase2LocalManualMappingAttempt).where(
                Phase2LocalManualMappingAttempt.attempt_id == "attempt-1"
            )
        )
        assert attempt is not None
        return str(
            session.scalar(
                select(Phase2LocalManualMappingAttemptEvent.state)
                .where(Phase2LocalManualMappingAttemptEvent.attempt_id == attempt.id)
                .order_by(Phase2LocalManualMappingAttemptEvent.sequence.desc())
            )
        )


def test_phase2_attempt_and_recovery_binding_exist_before_phase1_authorization(
    phase2_settings,
) -> None:
    upgrade_phase2_database(f"sqlite:///{phase2_settings.database_path}")
    engine = create_phase2_engine(phase2_settings)
    lock = Phase2InstanceLock.acquire(phase2_settings)
    coordinator = Phase2MutationCoordinator(phase2_settings, engine, lock)
    revision = _seed_candidate(
        coordinator, description="Bring a thoughtful approach."
    )
    inputs = _phase1_inputs().model_copy(
        update={
            "profile": _phase1_inputs().profile.model_copy(
                update={
                    "payload": _phase1_inputs().profile.payload.model_copy(
                        update={"eligible_roles": (revision.title,)}
                    )
                }
            )
        }
    )
    view = Phase2ActivationView("active", "", 1, 0, 0, "receipt-1", 1)

    class Activation:
        def revalidate_before(self, _action: object) -> Phase2ActivationView:
            return view

    class Publication:
        def capture_authority(self) -> _WitnessAuthority:
            return _WitnessAuthority()

    class Phase1:
        manifest: Phase1MatchingRetrievalManifest | None = None

        def activation_inputs(self) -> Phase1ActivationInputs:
            return inputs

        def matching_retrieval_manifest(
            self, query: Phase1MatchingRequirementQuery
        ) -> Phase1MatchingRetrievalManifest:
            requirement_id = query.requirement_ids[0]
            choice = Phase1MatchingManifestChoice(
                claim_id="claim-1",
                revision_id="fact-revision-1",
                support_assertion_id="support-1",
                safe_wording_sha256="f" * 64,
            )
            self.manifest = Phase1MatchingRetrievalManifest(
                query=query,
                query_fingerprint="a" * 64,
                choices=(choice,),
                edges=(
                    Phase1MatchingRelevanceEdge(
                        requirement_id=requirement_id,
                        claim_id=choice.claim_id,
                        matched_taxonomy_ids=("role_profile.senior_product_manager",),
                    ),
                ),
                candidate_universe_count=1,
                examined_count=1,
                omission_reason_counts=(),
                complete=True,
                structural_state="complete",
                semantic_state="complete",
                eligible_set_fingerprint="b" * 64,
                profile_fingerprint="a" * 64,
                profile_generation=1,
                readiness_fingerprint="b" * 64,
                readiness_generation=1,
                authority_fingerprint="c" * 64,
                authority_generation=1,
                restore_generation=0,
                disclosure_budget_epoch=1,
                disclosure_policy_generation=1,
                fingerprint="d" * 64,
            )
            return self.manifest

        def revalidate_matching_retrieval_manifest(
            self, expected: Phase1MatchingRetrievalManifest
        ) -> Phase1MatchingRetrievalManifest:
            return expected

        def authorize_matching_disclosure(
            self, request: object
        ) -> Phase1FactDisclosureAuthorizationSnapshot:
            attempt_id = request.context.attempt_id  # type: ignore[union-attr]
            with coordinator._session_factory() as session:
                stored = session.scalar(
                    select(Phase2LocalManualMappingAttempt).where(
                        Phase2LocalManualMappingAttempt.attempt_id == attempt_id
                    )
                )
            assert stored is not None
            assert stored.logical_payload_digest == request.logical_payload_digest  # type: ignore[union-attr]
            assert any(
                entry.event.event_type == "local_manual_mapping_authorized"
                and entry.event.payload.get("attempt_id") == attempt_id
                for entry in coordinator.recovery_ledger.read_all()
            )
            return Phase1FactDisclosureAuthorizationSnapshot(
                authorization_id=request.context.phase2_authorization_id,  # type: ignore[union-attr]
                attempt_id=attempt_id,
                nonce_sha256="a" * 64,
                manifest_fingerprint=request.context.manifest_fingerprint,  # type: ignore[union-attr]
                logical_payload_digest=request.logical_payload_digest,  # type: ignore[union-attr]
                disclosure_budget_epoch=1,
                disclosure_policy_generation=1,
                state="authorized",
                expires_at=request.context.expires_at,  # type: ignore[union-attr]
                fingerprint="f" * 64,
            )

        def release_matching_wording(self, request: object) -> Phase1MatchingWordingRelease:
            assert self.manifest is not None
            choice = self.manifest.choices[0]
            return Phase1MatchingWordingRelease(
                authorization_id=request.authorization.authorization_id,  # type: ignore[union-attr]
                logical_payload_digest=request.authorization.logical_payload_digest,  # type: ignore[union-attr]
                manifest_fingerprint=self.manifest.fingerprint,
                choices=(
                    Phase1MatchingReleasedChoice(
                        canonical_key="skills.product_management",
                        claim_id=choice.claim_id,
                        revision_id=choice.revision_id,
                        support_assertion_id=choice.support_assertion_id,
                        safe_wording="Approved product management evidence",
                        safe_wording_sha256=choice.safe_wording_sha256,
                    ),
                ),
                edges=self.manifest.edges,
                fingerprint="1" * 64,
            )

    service = CandidateWorkflowService(
        Phase1(),  # type: ignore[arg-type]
        Activation(),  # type: ignore[arg-type]
        coordinator,
        Publication(),  # type: ignore[arg-type]
        now=lambda: _NOW,
    )
    try:
        first = service.begin_local_manual_mapping(revision.id, "Hyderabad")
        retry = service.begin_local_manual_mapping(revision.id, "Hyderabad")
        assert first.requirements[0].component is ScoringComponent.EVIDENCE
        assert first.phase1_authorization_id == first.attempt_id
        assert retry.attempt_id != first.attempt_id
        assert retry.nonce != first.nonce
        assert retry.logical_payload_digest != first.logical_payload_digest
        assert retry.manifest_fingerprint == first.manifest_fingerprint
        assert retry.manifest.query == first.manifest.query
    finally:
        coordinator.dispose()
        lock.release()


def test_publication_accepts_a_qualified_provider_location(phase2_settings) -> None:
    service, phase1, publication, launch, selections, coordinator, lock = _recovery_service(
        phase2_settings, listing_locations=["Hyderabad, Telangana, India"]
    )
    try:
        assessment_id = service.publish_local_manual_mapping(launch, selections)

        assert assessment_id
        assert _attempt_state(coordinator) == "validated_response"
        assert phase1.lifecycle == ["consuming", "validated_response"]
        assert publication.calls == 1
    finally:
        coordinator.dispose()
        lock.release()


@pytest.mark.parametrize("start_failure", ("authorization", "release"))
def test_begin_mapping_settles_persisted_attempt_after_phase1_start_failure(
    phase2_settings,
    start_failure: Literal["authorization", "release"],
) -> None:
    upgrade_phase2_database(f"sqlite:///{phase2_settings.database_path}")
    engine = create_phase2_engine(phase2_settings)
    lock = Phase2InstanceLock.acquire(phase2_settings)
    coordinator = Phase2MutationCoordinator(phase2_settings, engine, lock)
    revision = _seed_candidate(coordinator)
    requirements = extract_public_requirements(revision)
    phase1 = _BeginningPhase1(_manifest(requirements[0]), start_failure)
    phase1.inputs = phase1.inputs.model_copy(
        update={
            "profile": phase1.inputs.profile.model_copy(
                update={
                    "payload": phase1.inputs.profile.payload.model_copy(
                        update={"eligible_roles": (revision.title,)}
                    )
                }
            )
        }
    )
    view = Phase2ActivationView("active", "", 1, 0, 0, "receipt-1", 1)

    class Activation:
        def revalidate_before(self, _action: object) -> Phase2ActivationView:
            return view

    class Publication:
        def capture_authority(self) -> _WitnessAuthority:
            return _WitnessAuthority()

    service = CandidateWorkflowService(
        phase1, Activation(), coordinator, Publication(), now=lambda: _NOW
    )
    try:
        with pytest.raises(CandidateWorkflowUnavailable, match="could not be started safely"):
            service.begin_local_manual_mapping(revision.id, "Hyderabad")

        with coordinator._session_factory() as session:
            attempt = session.scalar(select(Phase2LocalManualMappingAttempt))
            assert attempt is not None
            states = list(
                session.scalars(
                    select(Phase2LocalManualMappingAttemptEvent.state)
                    .where(Phase2LocalManualMappingAttemptEvent.attempt_id == attempt.id)
                    .order_by(Phase2LocalManualMappingAttemptEvent.sequence)
                )
            )
        assert states == ["authorized", "indeterminate"]
        assert phase1.lifecycle == ["indeterminate"]
        terminal_events = [
            entry.event
            for entry in coordinator.recovery_ledger.read_all()
            if entry.event.event_type == "local_manual_mapping_terminal"
        ]
        assert len(terminal_events) == 1
        assert terminal_events[0].payload == {
            "attempt_id": attempt.attempt_id,
            "state": "indeterminate",
            "reason_code": f"phase1_{start_failure}_unavailable",
        }
    finally:
        coordinator.dispose()
        lock.release()


def test_failure_before_phase1_consuming_seals_both_stores_and_denies_replay(
    phase2_settings,
) -> None:
    service, phase1, publication, launch, selections, coordinator, lock = _recovery_service(
        phase2_settings, phase1_failure="before_consuming"
    )
    try:
        with pytest.raises(RuntimeError, match="before Phase I consuming"):
            service.publish_local_manual_mapping(launch, selections)

        assert _attempt_state(coordinator) == "failed"
        assert phase1.lifecycle == ["failed"]
        with pytest.raises(CandidateWorkflowUnavailable, match="cannot be replayed"):
            service.publish_local_manual_mapping(launch, selections)
        assert publication.calls == 0
        assert phase1.manifest_calls == 1
    finally:
        coordinator.dispose()
        lock.release()


def test_phase1_expiry_between_recovery_checks_commits_the_same_expired_terminal(
    phase2_settings,
) -> None:
    service, phase1, _publication, launch, selections, coordinator, lock = _recovery_service(
        phase2_settings,
        phase1_failure="before_consuming",
        phase1_expires_on_terminal=True,
    )
    try:
        with pytest.raises(RuntimeError, match="before Phase I consuming"):
            service.publish_local_manual_mapping(launch, selections)

        assert _attempt_state(coordinator) == "expired"
        assert phase1.lifecycle == ["expired"]
        with pytest.raises(CandidateWorkflowUnavailable, match="cannot be replayed"):
            service.publish_local_manual_mapping(launch, selections)
    finally:
        coordinator.dispose()
        lock.release()


def test_phase1_consuming_receipt_expiry_blocks_publication_and_seals_phase2(
    phase2_settings,
) -> None:
    service, phase1, publication, launch, selections, coordinator, lock = _recovery_service(
        phase2_settings,
        phase1_consuming_receipt_state="expired",
    )
    try:
        with pytest.raises(CandidateWorkflowUnavailable, match="did not enter consuming"):
            service.publish_local_manual_mapping(launch, selections)

        assert _attempt_state(coordinator) == "expired"
        assert phase1.lifecycle == ["expired"]
        assert publication.calls == 0
        with coordinator._session_factory() as session:
            assert session.scalar(select(Phase2MatchAssessment)) is None
    finally:
        coordinator.dispose()
        lock.release()


def test_recovery_seals_phase2_after_a_crash_between_phase1_and_phase2_terminals(
    phase2_settings,
) -> None:
    service, phase1, _publication, launch, selections, coordinator, lock = _recovery_service(
        phase2_settings
    )
    try:
        assessment_id = str(
            uuid5(
                NAMESPACE_URL,
                "phase2-local-manual-assessment:"
                f"{launch.attempt_id}:{launch.logical_payload_digest}",
            )
        )
        service._record_publication_intent(launch, assessment_id)
        assert service._record_phase1_terminal(launch, "failed", "publication_failed") == "failed"

        with pytest.raises(CandidateWorkflowUnavailable, match="cannot be replayed"):
            service.publish_local_manual_mapping(launch, selections)
        assert _attempt_state(coordinator) == "failed"
        assert phase1.lifecycle == ["failed"]
    finally:
        coordinator.dispose()
        lock.release()


def test_interruption_after_phase1_consuming_recovers_as_indeterminate_and_denies_replay(
    phase2_settings,
) -> None:
    service, phase1, publication, launch, selections, coordinator, lock = _recovery_service(
        phase2_settings, phase1_failure="after_consuming"
    )
    try:
        with pytest.raises(KeyboardInterrupt, match="after Phase I consuming"):
            service.publish_local_manual_mapping(launch, selections)

        assert _attempt_state(coordinator) == "authorized"
        assert phase1.lifecycle == ["consuming"]
        with pytest.raises(CandidateWorkflowUnavailable, match="cannot be replayed"):
            service.publish_local_manual_mapping(launch, selections)
        assert _attempt_state(coordinator) == "indeterminate"
        assert phase1.lifecycle == ["consuming", "indeterminate"]
        assert publication.calls == 0
        with pytest.raises(CandidateWorkflowUnavailable, match="cannot be replayed"):
            service.publish_local_manual_mapping(launch, selections)
    finally:
        coordinator.dispose()
        lock.release()


def test_assessment_witness_recovers_a_crash_before_phase2_terminal_and_completes_phase1(
    phase2_settings,
) -> None:
    service, phase1, publication, launch, selections, coordinator, lock = _recovery_service(
        phase2_settings, interrupt_after_assessment=True
    )
    try:
        with pytest.raises(KeyboardInterrupt, match="after Phase II assessment publication"):
            service.publish_local_manual_mapping(launch, selections)

        assert _attempt_state(coordinator) == "authorized"
        assert phase1.lifecycle == ["consuming"]
        recovered = service.publish_local_manual_mapping(launch, selections)

        assert recovered == service.publish_local_manual_mapping(launch, selections)
        assert _attempt_state(coordinator) == "validated_response"
        assert phase1.lifecycle == ["consuming", "validated_response"]
        assert publication.calls == 1
        with coordinator._session_factory() as session:
            assert (
                session.scalar(
                    select(Phase2MatchAssessment).where(Phase2MatchAssessment.id == recovered)
                )
                is not None
            )
    finally:
        coordinator.dispose()
        lock.release()


def test_exception_after_committed_assessment_reconciles_the_witness_before_failing(
    phase2_settings,
) -> None:
    service, phase1, publication, launch, selections, coordinator, lock = _recovery_service(
        phase2_settings, fail_after_assessment=True
    )
    try:
        recovered = service.publish_local_manual_mapping(launch, selections)

        assert recovered == service.publish_local_manual_mapping(launch, selections)
        assert _attempt_state(coordinator) == "validated_response"
        assert phase1.lifecycle == ["consuming", "validated_response"]
        assert publication.calls == 1
    finally:
        coordinator.dispose()
        lock.release()


def test_recovery_rejects_an_assessment_witness_with_a_wrong_manifest_binding(
    phase2_settings,
) -> None:
    service, phase1, _publication, launch, selections, coordinator, lock = _recovery_service(
        phase2_settings, interrupt_after_assessment=True, corrupt_witness=True
    )
    try:
        with pytest.raises(KeyboardInterrupt, match="after Phase II assessment publication"):
            service.publish_local_manual_mapping(launch, selections)

        with pytest.raises(CandidateWorkflowUnavailable, match="witness is inconsistent"):
            service.publish_local_manual_mapping(launch, selections)
        assert _attempt_state(coordinator) == "authorized"
        assert phase1.lifecycle == ["consuming"]
    finally:
        coordinator.dispose()
        lock.release()


@pytest.mark.parametrize("component_witness_corruption", ("duplicate_name", "wrong_score"))
def test_recovery_rejects_an_assessment_witness_with_malformed_components(
    phase2_settings,
    component_witness_corruption: Literal["duplicate_name", "wrong_score"],
) -> None:
    service, phase1, _publication, launch, selections, coordinator, lock = _recovery_service(
        phase2_settings,
        interrupt_after_assessment=True,
        component_witness_corruption=component_witness_corruption,
    )
    try:
        with pytest.raises(KeyboardInterrupt, match="after Phase II assessment publication"):
            service.publish_local_manual_mapping(launch, selections)

        with pytest.raises(CandidateWorkflowUnavailable, match="witness is inconsistent"):
            service.publish_local_manual_mapping(launch, selections)
        assert _attempt_state(coordinator) == "authorized"
        assert phase1.lifecycle == ["consuming"]
    finally:
        coordinator.dispose()
        lock.release()


def test_recovery_rejects_an_assessment_witness_with_none_mapping_fact_identifiers(
    phase2_settings,
) -> None:
    service, phase1, _publication, launch, selections, coordinator, lock = _recovery_service(
        phase2_settings,
        interrupt_after_assessment=True,
        none_mapping_identifiers=True,
        selection_relation=EvidenceRelation.NONE,
    )
    try:
        with pytest.raises(KeyboardInterrupt, match="after Phase II assessment publication"):
            service.publish_local_manual_mapping(launch, selections)

        with pytest.raises(CandidateWorkflowUnavailable, match="witness is inconsistent"):
            service.publish_local_manual_mapping(launch, selections)
        assert _attempt_state(coordinator) == "authorized"
        assert phase1.lifecycle == ["consuming"]
    finally:
        coordinator.dispose()
        lock.release()


def test_in_mutation_guard_rejects_a_revision_that_became_stale_after_precheck(
    phase2_settings,
) -> None:
    service, phase1, publication, launch, selections, coordinator, lock = _recovery_service(
        phase2_settings, insert_stale_revision=True
    )
    try:
        with pytest.raises(CandidateWorkflowUnavailable, match="job revision is not current"):
            service.publish_local_manual_mapping(launch, selections)

        assert publication.expected_authority is launch.authority
        assert _attempt_state(coordinator) == "failed"
        assert phase1.lifecycle == ["consuming", "failed"]
        with coordinator._session_factory() as session:
            assert session.scalar(select(Phase2MatchAssessment)) is None
    finally:
        coordinator.dispose()
        lock.release()


def test_local_manual_mapping_attempt_schema_is_append_only(phase2_settings) -> None:
    upgrade_phase2_database(f"sqlite:///{phase2_settings.database_path}")
    engine = create_phase2_engine(phase2_settings)
    try:
        tables = set(inspect(engine).get_table_names())
        mapping_tables = {
            "phase2_local_manual_mapping_attempts",
            "phase2_local_manual_mapping_attempt_events",
        }
        assert mapping_tables <= tables
        forbidden = {"wording", "safe_wording", "content", "secret", "token"}
        for table in mapping_tables:
            columns = {column["name"] for column in inspect(engine).get_columns(table)}
            assert not columns.intersection(forbidden)
        columns = {
            column["name"]
            for column in inspect(engine).get_columns("phase2_local_manual_mapping_attempts")
        }
        assert {"logical_payload_digest", "manifest_fingerprint", "nonce_sha256"} <= columns
        mapping_columns = {
            column["name"] for column in inspect(engine).get_columns("phase2_requirement_mappings")
        }
        assert "canonical_fact_key" in mapping_columns
    finally:
        engine.dispose()
    with sqlite3.connect(phase2_settings.database_path) as connection:
        for table in mapping_tables:
            triggers = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name = ?",
                    (table,),
                )
            }
            assert {f"prevent_{table}_update", f"prevent_{table}_delete"} <= triggers
        connection.execute(
            """
            INSERT INTO phase2_local_manual_mapping_attempts (
                id, attempt_id, nonce_sha256, phase1_authorization_id, job_revision_id,
                selected_location_path_fingerprint, coverage_ledger_fingerprint,
                manifest_fingerprint, logical_payload_digest, rubric_version,
                retrieval_configuration_version, interpreter_configuration_version,
                response_schema_version, expires_at, state, created_at,
                phase1_profile_fingerprint, phase1_profile_generation,
                phase1_readiness_fingerprint, phase1_readiness_generation,
                phase1_authority_fingerprint, phase1_authority_generation,
                phase1_restore_generation, phase2_activation_generation,
                phase2_restore_generation
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "attempt-row",
                "attempt-1",
                "a" * 64,
                "phase1-auth",
                "revision-1",
                "b" * 64,
                "c" * 64,
                "d" * 64,
                "e" * 64,
                "rubric-v1",
                "retrieval-v1",
                "local-manual-v1",
                "schema-v1",
                "2026-09-01T00:00:00+00:00",
                "authorized",
                "2026-08-31T00:00:00+00:00",
                "f" * 64,
                1,
                "1" * 64,
                1,
                "2" * 64,
                1,
                0,
                1,
                0,
            ),
        )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("UPDATE phase2_local_manual_mapping_attempts SET state = 'failed'")
