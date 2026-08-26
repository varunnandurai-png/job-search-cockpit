import pytest

from job_search_cockpit.phase1_contract.snapshots import Phase1ResumeFactProjection
from job_search_cockpit.phase2.assessment import (
    AssessmentEvidenceService,
    AssessmentUnavailable,
    ComponentContribution,
    calculate_component_score,
)
from job_search_cockpit.phase2.assessment_types import (
    ConfidenceState,
    EvidenceRelation,
    GateResult,
    MatchScoreComponents,
    RequirementKind,
)


def test_match_score_components_total_the_approved_maximum() -> None:
    components = MatchScoreComponents(
        role=25,
        domain=20,
        responsibility=15,
        technical=15,
        outcome=10,
        seniority=10,
        evidence=5,
    )

    assert components.total == 100


def test_match_score_components_reject_a_component_above_its_approved_maximum() -> None:
    with pytest.raises(ValueError, match="role score exceeds its approved maximum"):
        MatchScoreComponents(
            role=26,
            domain=20,
            responsibility=15,
            technical=15,
            outcome=10,
            seniority=10,
            evidence=5,
        )


def test_assessment_states_are_bounded_to_the_approved_vocabulary() -> None:
    assert GateResult.PASS.value == "pass"
    assert RequirementKind.REQUIRED.value == "required"
    assert EvidenceRelation.ADJACENT.value == "adjacent"
    assert ConfidenceState.BLOCKED.value == "blocked"


def test_component_score_caps_duplicate_evidence_at_its_fixed_maximum() -> None:
    score = calculate_component_score(
        25,
        (
            ComponentContribution("requirement-1", 20, EvidenceRelation.DIRECT),
            ComponentContribution("requirement-1", 20, EvidenceRelation.DIRECT),
            ComponentContribution("requirement-2", 20, EvidenceRelation.DIRECT),
        ),
    )

    assert score == 25


def test_evidence_service_blocks_a_projection_with_an_unmet_requirement() -> None:
    projection = Phase1ResumeFactProjection(
        requirement_ids=("role.product",),
        facts=(),
        profile_fingerprint="a" * 64,
        profile_generation=1,
        readiness_fingerprint="b" * 64,
        readiness_generation=1,
        authority_fingerprint="c" * 64,
        authority_generation=1,
        restore_generation=0,
        fingerprint="d" * 64,
    )

    service = AssessmentEvidenceService(_ProjectionPort(projection))

    with pytest.raises(AssessmentUnavailable, match="approved evidence"):
        service.require_complete_evidence(("role.product",))


class _ProjectionPort:
    def __init__(self, projection: Phase1ResumeFactProjection) -> None:
        self.projection = projection

    def resume_fact_projection(self, _request: object) -> Phase1ResumeFactProjection:
        return self.projection

    def revalidate_resume_fact_projection(
        self, _expected: Phase1ResumeFactProjection
    ) -> Phase1ResumeFactProjection:
        return self.projection
