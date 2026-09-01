from datetime import UTC, datetime

import pytest

from job_search_cockpit.phase2.assessment import (
    AssessmentAuthorityService,
    AssessmentPublicationCommand,
    AssessmentPublicationService,
    AssessmentUnavailable,
)
from job_search_cockpit.phase2.assessment_types import (
    ConfidenceState,
    EvidenceRelation,
    GateResult,
    LocationEligibilityPath,
    MatchAssessmentResult,
    MatchScoreComponents,
    QualifiedMatchBand,
    Requirement,
    RequirementEvidenceMapping,
    RequirementKind,
    ScoringComponent,
)
from job_search_cockpit.phase2.models import (
    Phase2JobRevision,
    Phase2LocationEligibilityPath,
    Phase2MatchAssessment,
    Phase2MatchComponent,
    Phase2RequirementMapping,
    Phase2ShortlistDecision,
)
from job_search_cockpit.phase2.shortlist import (
    AssessmentReviewItem,
    AssessmentReviewService,
)
from job_search_cockpit.phase2.types import ActivationCommand
from tests.integration.test_phase2_activation import _service
from tests.support.web import authenticated_test_app, build_test_app


class _DriftingAuthority:
    def capture_for_assessment(self) -> object:
        return object()

    def revalidate_before_publication(self, expected: object) -> object:
        del expected
        raise AssessmentUnavailable("Assessment authority changed before publication.")


class _NoWriteCoordinator:
    def run(self, operation: object, reason: str, *, actor: str = "system") -> object:
        del operation, reason, actor
        raise AssertionError(
            "publication must not enter a mutation transaction after authority drift"
        )


class _OpaqueAuthoritySnapshot:
    def __init__(self) -> None:
        self.phase1_inputs = type(
            "Inputs", (), {"profile": type("Profile", (), {"fingerprint": "a" * 64})()}
        )()

    def persistence_fields(self) -> dict[str, str | int]:
        return {
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


class _StableOpaqueAuthority:
    def __init__(self) -> None:
        self.snapshot = _OpaqueAuthoritySnapshot()

    def capture_for_assessment(self) -> _OpaqueAuthoritySnapshot:
        return self.snapshot

    def revalidate_before_publication(
        self, expected: _OpaqueAuthoritySnapshot
    ) -> _OpaqueAuthoritySnapshot:
        assert expected is self.snapshot
        return self.snapshot


class _RecordingSession:
    def __init__(self) -> None:
        self.records: list[object] = []

    def get(self, model: object, identifier: str) -> object | None:
        if model is Phase2JobRevision and identifier == "revision-1":
            return object()
        return None

    def add(self, record: object) -> None:
        self.records.append(record)


class _RecordingCoordinator:
    def __init__(self) -> None:
        self.session = _RecordingSession()

    def run(self, operation: object, reason: str, *, actor: str = "system") -> object:
        del reason, actor
        return operation(self.session)  # type: ignore[operator]


class _StaticAssessmentReviewStore:
    def __init__(self, items: tuple[AssessmentReviewItem, ...]) -> None:
        self.items = items

    def current_items(self, snapshot: _OpaqueAuthoritySnapshot) -> tuple[AssessmentReviewItem, ...]:
        assert snapshot.persistence_fields()["phase2_activation_generation"] == 1
        return self.items


def _publication_command() -> AssessmentPublicationCommand:
    requirement = Requirement(
        requirement_id="requirements.role",
        kind=RequirementKind.REQUIRED,
        component=ScoringComponent.ROLE,
        source_span_id="span-1",
        start_offset=0,
        end_offset=10,
    )
    return AssessmentPublicationCommand(
        result=MatchAssessmentResult(
            assessment_id="assessment-1",
            job_revision_id="revision-1",
            components=MatchScoreComponents(20, 20, 20, 10, 15, 10, 5),
            qualified_band=QualifiedMatchBand.STRONG,
            confidence=ConfidenceState.HIGH,
            hard_gates_pass=True,
            current=True,
            critical_floors_pass=True,
            meaningful_role_and_responsibility=True,
            worthwhile_structure=True,
            unsupported_required=False,
        ),
        requirements=(requirement,),
        mappings=(
            RequirementEvidenceMapping(
                requirement_id=requirement.requirement_id,
                relation=EvidenceRelation.DIRECT,
                reason_code="direct/exact_capability_performed",
                claim_id="claim-1",
                revision_id="revision-1",
                support_assertion_id="support-1",
            ),
        ),
        gate_result=GateResult.PASS,
        gate_reason_codes=("eligible_role",),
        location_paths=(LocationEligibilityPath("location-1", GateResult.PASS, ("eligible",)),),
        rubric_version="rubric-v1",
        coverage_ledger_fingerprint="d" * 64,
        fact_set_fingerprint="e" * 64,
        assessment_state="stable",
        shortlist_reason_codes=("qualified_match",),
        canonical_fact_keys=((requirement.requirement_id, "skills.product_management"),),
    )


def test_assessment_publication_rejects_phase1_drift_after_authority_capture(
    phase2_settings,
) -> None:
    with _service(phase2_settings) as (activation_service, phase1_port):
        activation_service.activate(
            ActivationCommand(actor="Varun", confirmation="ENABLE PHASE II")
        )
        authority_service = AssessmentAuthorityService(phase1_port, activation_service)
        captured = authority_service.capture_for_assessment()
        phase1_port.current = phase1_port.current.model_copy(
            update={
                "readiness": phase1_port.current.readiness.model_copy(
                    update={"readiness_generation": 2}
                )
            }
        )

        with pytest.raises(AssessmentUnavailable, match="authority changed"):
            authority_service.revalidate_before_publication(captured)


def test_publication_refuses_to_enter_a_mutation_when_authority_drifts() -> None:
    service = AssessmentPublicationService(_DriftingAuthority(), _NoWriteCoordinator())

    with pytest.raises(AssessmentUnavailable, match="authority changed"):
        service.publish(None)  # type: ignore[arg-type]


def test_publication_appends_only_opaque_assessment_metadata() -> None:
    coordinator = _RecordingCoordinator()
    service = AssessmentPublicationService(_StableOpaqueAuthority(), coordinator)  # type: ignore[arg-type]

    assert service.publish(_publication_command()) == "assessment-1"
    assert (
        sum(isinstance(record, Phase2MatchAssessment) for record in coordinator.session.records)
        == 1
    )
    assert (
        sum(isinstance(record, Phase2MatchComponent) for record in coordinator.session.records) == 7
    )
    assert (
        sum(isinstance(record, Phase2RequirementMapping) for record in coordinator.session.records)
        == 1
    )
    assert (
        sum(isinstance(record, Phase2ShortlistDecision) for record in coordinator.session.records)
        == 1
    )
    location = next(
        record
        for record in coordinator.session.records
        if isinstance(record, Phase2LocationEligibilityPath)
    )
    assert location.location_fingerprint != "location-1"


def test_current_review_returns_only_fenced_eligible_assessments() -> None:
    now = datetime(2026, 8, 27, tzinfo=UTC)
    service = AssessmentReviewService(
        _StableOpaqueAuthority(),  # type: ignore[arg-type]
        _StaticAssessmentReviewStore(
            (
                AssessmentReviewItem(
                    assessment_id="assessment-current",
                    score=90,
                    qualified_band="strong",
                    confidence=ConfidenceState.HIGH,
                    decision="focused",
                    assessment_state="stable",
                    created_at=now,
                ),
                AssessmentReviewItem(
                    assessment_id="assessment-excluded",
                    score=100,
                    qualified_band="strong",
                    confidence=ConfidenceState.HIGH,
                    decision="not_focused",
                    assessment_state="stable",
                    created_at=now,
                ),
            )
        ),
    )

    view = service.current_view()

    assert view.current is True
    assert [item.assessment_id for item in view.focused] == ["assessment-current"]
    assert all(item.score >= 70 for item in view.focused)


def test_assessment_view_is_authenticated_and_redacted_without_current_authority(
    vault_settings,
) -> None:
    with authenticated_test_app(vault_settings) as client:
        response = client.get("/phase-2/assessments")

    assert response.status_code == 200
    assert "Current match assessments are unavailable." in response.text
    assert "safe wording" not in response.text.lower()


def test_assessment_view_rejects_a_request_without_the_local_launch_session(
    vault_settings,
) -> None:
    with build_test_app(vault_settings) as (_, client):
        response = client.get("/phase-2/assessments")

    assert response.status_code == 401
    assert "Launch session required." in response.text
