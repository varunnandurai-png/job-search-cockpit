from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from job_search_cockpit.phase1_contract.snapshots import (
    Phase1AcceptanceReceiptSnapshot,
    Phase1ActivationInputs,
    Phase1ReadinessSnapshot,
    Phase1ResumeFactProjection,
    Phase1ResumeFactProjectionRequest,
    Phase1ResumeFactSnapshot,
    SearchProfileSnapshot,
)
from job_search_cockpit.phase2.assessment_types import EvidenceRelation, RequirementKind
from job_search_cockpit.phase2.config import Phase2Settings
from job_search_cockpit.phase2.database import create_phase2_engine, upgrade_phase2_database
from job_search_cockpit.phase2.models import (
    Phase2DiscoveryRun,
    Phase2JobGateAssessment,
    Phase2JobRecord,
    Phase2JobRevision,
    Phase2MatchAssessment,
    Phase2RequirementMapping,
    Phase2ResumeRequirementLedger,
    Phase2SourceListingObservation,
)
from job_search_cockpit.phase2.mutation import Phase2InstanceLock, Phase2MutationCoordinator
from job_search_cockpit.phase2.resume_safety import ResumePreparationError
from job_search_cockpit.phase2.types import Phase2ActivationView
from job_search_cockpit.phase2.verification import (
    VerifiedJobAuthorizationService,
    VerifyCandidateCommand,
    _as_utc,
)
from job_search_cockpit.search_profile.catalog import build_profile_v1


def test_verification_expiry_normalizes_sqlite_naive_datetimes_to_utc() -> None:
    normalized = _as_utc(datetime(2026, 8, 26, 12, 0))

    assert normalized == datetime(2026, 8, 26, 12, 0, tzinfo=UTC)


_NOW = datetime(2026, 9, 1, tzinfo=UTC)
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


class _Phase1:
    def __init__(self, canonical_keys: tuple[str, ...]) -> None:
        self.inputs = _inputs()
        self.canonical_keys = canonical_keys

    def activation_inputs(self) -> Phase1ActivationInputs:
        return self.inputs

    def revalidate_activation_inputs(
        self, expected: Phase1ActivationInputs
    ) -> Phase1ActivationInputs:
        assert expected == self.inputs
        return self.inputs

    def resume_fact_projection(
        self, request: Phase1ResumeFactProjectionRequest
    ) -> Phase1ResumeFactProjection:
        assert set(request.requirement_ids) <= set(self.canonical_keys)
        facts = tuple(
            Phase1ResumeFactSnapshot(
                requirement_id=key,
                claim_id=f"claim-{key}",
                revision_id=f"revision-{key}",
                support_assertion_id=f"support-{key}",
                safe_wording="Approved evidence.",
                employer_key=None,
                period_start=None,
                period_end=None,
            )
            for key in request.requirement_ids
        )
        return Phase1ResumeFactProjection(
            requirement_ids=request.requirement_ids,
            facts=facts,
            profile_fingerprint="a" * 64,
            profile_generation=1,
            readiness_fingerprint="b" * 64,
            readiness_generation=1,
            authority_fingerprint="c" * 64,
            authority_generation=1,
            restore_generation=0,
            fingerprint="d" * 64,
        )

    def revalidate_resume_fact_projection(
        self, expected: Phase1ResumeFactProjection
    ) -> Phase1ResumeFactProjection:
        return expected


class _ActivePhase2:
    view = Phase2ActivationView("active", "", 1, 0, 0, "receipt-1", 1)

    def revalidate_before(self, _action: object) -> Phase2ActivationView:
        return self.view


def _inputs() -> Phase1ActivationInputs:
    return Phase1ActivationInputs(
        acceptance_receipt=Phase1AcceptanceReceiptSnapshot(
            id="receipt-1",
            application_build="test",
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
            import_run_id="run-1",
            source_hashes={"test": "s" * 64},
            active_profile_version=1,
            authority_high_water_mark=1,
            readiness_generation=1,
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


def _service(
    settings: Phase2Settings,
    keys: tuple[str, ...],
    *,
    relation: str = EvidenceRelation.DIRECT.value,
    canonical_key: object = ...,
) -> tuple[VerifiedJobAuthorizationService, Phase2MutationCoordinator, Phase2InstanceLock]:
    upgrade_phase2_database(f"sqlite:///{settings.database_path}")
    engine = create_phase2_engine(settings)
    lock = Phase2InstanceLock.acquire(settings)
    coordinator = Phase2MutationCoordinator(settings, engine, lock)
    _seed(coordinator, keys, relation=relation, canonical_key=canonical_key)
    return (
        VerifiedJobAuthorizationService(
            _Phase1(keys), _ActivePhase2(), coordinator, now=lambda: _NOW
        ),  # type: ignore[arg-type]
        coordinator,
        lock,
    )


def _seed(
    coordinator: Phase2MutationCoordinator,
    keys: tuple[str, ...],
    *,
    relation: str,
    canonical_key: object,
) -> None:
    def insert(session: Session) -> None:
        session.add(Phase2DiscoveryRun(id="run-1", **_FENCE))
        session.flush()
        session.add(
            Phase2SourceListingObservation(
                id="observation-1",
                discovery_run_id="run-1",
                provider_id="test",
                provider_run_id=None,
                source_listing_id="listing-1",
                canonical_url="https://example.test/1",
                title="Product Manager",
                employer_name="Example",
                locations_json=["Hyderabad"],
                posted_at=None,
                public_description="A public description.",
                compensation_text=None,
                retrieved_at=_NOW,
                raw_content_fingerprint="e" * 64,
                content_fingerprint="f" * 64,
            )
        )
        session.flush()
        session.add(Phase2JobRecord(id="job-1", posting_identity_fingerprint="g" * 64))
        session.flush()
        session.add(
            Phase2JobRevision(
                id="revision-1",
                job_record_id="job-1",
                source_observation_id="observation-1",
                canonical_url="https://example.test/1",
                title="Product Manager",
                employer_name="Example",
                locations_json=["Hyderabad"],
                posted_at=None,
                public_description="A public description.",
                compensation_text=None,
                content_fingerprint="h" * 64,
                created_at=_NOW,
            )
        )
        session.flush()
        session.add(
            Phase2JobGateAssessment(
                id="gate-1",
                job_revision_id="revision-1",
                profile_fingerprint="a" * 64,
                result="pass",
                reason_codes_json=["eligible"],
                **_FENCE,
            )
        )
        session.flush()
        session.add(
            Phase2MatchAssessment(
                id="assessment-1",
                job_revision_id="revision-1",
                job_gate_assessment_id="gate-1",
                rubric_version="test",
                coverage_ledger_fingerprint="i" * 64,
                total_score=80,
                qualified_band="strong",
                critical_floors_pass=True,
                meaningful_role_and_responsibility=True,
                worthwhile_structure=True,
                unsupported_required=False,
                confidence="high",
                assessment_state="stable",
                fact_set_fingerprint="j" * 64,
                **_FENCE,
            )
        )
        for index, key in enumerate(keys):
            session.add(
                Phase2RequirementMapping(
                    id=f"mapping-{index}",
                    match_assessment_id="assessment-1",
                    requirement_id=f"job.revision-1.required.{index}",
                    requirement_kind=RequirementKind.REQUIRED.value,
                    component="evidence",
                    source_span_id=f"span-{index}",
                    source_start_offset=index * 10,
                    source_end_offset=index * 10 + 5,
                    claim_id=f"claim-{key}",
                    fact_revision_id=f"revision-{key}",
                    support_assertion_id=f"support-{key}",
                    canonical_fact_key=(key if canonical_key is ... else canonical_key),
                    relation=relation,
                    reason_code="direct/exact_capability_performed",
                    **_FENCE,
                )
            )

    coordinator.run(insert, "seed_verification_ledger")


def _command() -> VerifyCandidateCommand:
    return VerifyCandidateCommand(
        job_revision_id="revision-1",
        selected_location_path="Hyderabad",
        actor="tester",
        reason="verify",
        confirmation="VERIFY JOB FOR PHASE II PREPARATION",
        eligibility="ineligible",
        unknown_mandatory_rule_codes=("posted_state_is_ignored",),
    )


def test_verification_issues_only_canonical_phase1_keys_in_first_requirement_order_and_reuses_it(
    phase2_settings: Phase2Settings,
) -> None:
    service, coordinator, lock = _service(phase2_settings, ("skills.python", "skills.product"))
    try:
        first = service.verify(_command())
        second = service.verify(_command())
        with coordinator._session_factory() as session:
            ledgers = tuple(session.scalars(select(Phase2ResumeRequirementLedger)))
        assert first.requirement_ids == ("skills.python", "skills.product")
        assert second.requirement_ledger_fingerprint == first.requirement_ledger_fingerprint
        assert len(ledgers) == 1
        assert ledgers[0].requirement_ids_json == ["skills.python", "skills.product"]
        assert all(not key.startswith("job.") for key in ledgers[0].requirement_ids_json)
    finally:
        coordinator.dispose()
        lock.release()


def test_verification_issues_a_new_ledger_when_the_current_assessment_changes(
    phase2_settings: Phase2Settings,
) -> None:
    service, coordinator, lock = _service(phase2_settings, ("skills.python", "skills.product"))
    try:
        first = service.verify(_command())

        def append_assessment(session: Session) -> None:
            session.add(
                Phase2JobGateAssessment(
                    id="gate-2",
                    job_revision_id="revision-1",
                    profile_fingerprint="a" * 64,
                    result="pass",
                    reason_codes_json=["eligible"],
                    **_FENCE,
                )
            )
            session.flush()
            session.add(
                Phase2MatchAssessment(
                    id="assessment-2",
                    job_revision_id="revision-1",
                    job_gate_assessment_id="gate-2",
                    rubric_version="test",
                    coverage_ledger_fingerprint="k" * 64,
                    total_score=80,
                    qualified_band="strong",
                    critical_floors_pass=True,
                    meaningful_role_and_responsibility=True,
                    worthwhile_structure=True,
                    unsupported_required=False,
                    confidence="high",
                    assessment_state="stable",
                    fact_set_fingerprint="l" * 64,
                    created_at=_NOW + timedelta(days=1),
                    **_FENCE,
                )
            )
            session.add(
                Phase2RequirementMapping(
                    id="mapping-2",
                    match_assessment_id="assessment-2",
                    requirement_id="job.revision-1.required.2",
                    requirement_kind=RequirementKind.REQUIRED.value,
                    component="evidence",
                    source_span_id="span-2",
                    source_start_offset=20,
                    source_end_offset=25,
                    claim_id="claim-skills.product",
                    fact_revision_id="revision-skills.product",
                    support_assertion_id="support-skills.product",
                    canonical_fact_key="skills.product",
                    relation=EvidenceRelation.DIRECT.value,
                    reason_code="direct/exact_capability_performed",
                    **_FENCE,
                )
            )

        coordinator.run(append_assessment, "append_changed_assessment")
        second = service.verify(_command())
        with coordinator._session_factory() as session:
            ledgers = tuple(
                session.scalars(
                    select(Phase2ResumeRequirementLedger).order_by(
                        Phase2ResumeRequirementLedger.created_at,
                        Phase2ResumeRequirementLedger.id,
                    )
                )
            )
        assert first.requirement_ids == ("skills.python", "skills.product")
        assert second.requirement_ids == ("skills.product",)
        assert second.requirement_ledger_fingerprint != first.requirement_ledger_fingerprint
        assert len(ledgers) == 2
    finally:
        coordinator.dispose()
        lock.release()


@pytest.mark.parametrize(
    ("relation", "canonical_key", "message"),
    (
        (EvidenceRelation.ADJACENT.value, "skills.python", "unsupported mandatory"),
        (EvidenceRelation.DIRECT.value, None, "assessment mappings are unavailable"),
        (EvidenceRelation.NONE.value, "skills.python", "assessment mappings are unavailable"),
    ),
)
def test_verification_rejects_unsupported_or_unbound_requirement_mappings(
    phase2_settings: Phase2Settings,
    relation: str,
    canonical_key: str | None,
    message: str,
) -> None:
    service, coordinator, lock = _service(
        phase2_settings, ("skills.python",), relation=relation, canonical_key=canonical_key
    )
    try:
        with pytest.raises(ResumePreparationError, match=message):
            service.verify(_command())
    finally:
        coordinator.dispose()
        lock.release()
