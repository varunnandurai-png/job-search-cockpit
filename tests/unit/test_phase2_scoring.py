import pytest

from job_search_cockpit.phase1_contract.snapshots import Phase1ResumeFactProjection
from job_search_cockpit.phase2.assessment import (
    AssessmentEvidenceService,
    AssessmentUnavailable,
    ComponentContribution,
    ComponentRequirement,
    anchor_points,
    calculate_component_score,
    component_anchor,
)
from job_search_cockpit.phase2.assessment_types import (
    ComponentAnchor,
    ConfidenceState,
    EvidenceRelation,
    GateResult,
    MatchScoreComponents,
    RequirementKind,
)


def test_match_score_components_total_the_approved_maximum() -> None:
    components = MatchScoreComponents(
        role=20,
        domain=20,
        responsibility=20,
        technical=10,
        outcome=15,
        seniority=10,
        evidence=5,
    )

    assert components.total == 100


def test_match_score_components_reject_a_component_above_its_approved_maximum() -> None:
    with pytest.raises(ValueError, match="role score exceeds its approved maximum"):
        MatchScoreComponents(
            role=21,
            domain=20,
            responsibility=20,
            technical=10,
            outcome=15,
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
        20,
        (
            ComponentContribution("requirement-1", 20, EvidenceRelation.DIRECT),
            ComponentContribution("requirement-1", 20, EvidenceRelation.DIRECT),
            ComponentContribution("requirement-2", 20, EvidenceRelation.DIRECT),
        ),
    )

    assert score == 20


def test_component_anchor_requires_two_direct_requirements_for_close() -> None:
    anchor = component_anchor(
        (
            ComponentRequirement("role.one", RequirementKind.REQUIRED, EvidenceRelation.DIRECT),
            ComponentRequirement(
                "role.two", RequirementKind.MATERIAL_RESPONSIBILITY, EvidenceRelation.DIRECT
            ),
        )
    )

    assert anchor is ComponentAnchor.CLOSE


def test_single_direct_requirement_is_capped_at_strong() -> None:
    anchor = component_anchor(
        (ComponentRequirement("role.one", RequirementKind.REQUIRED, EvidenceRelation.DIRECT),)
    )

    assert anchor is ComponentAnchor.STRONG


def test_anchor_points_use_only_the_approved_discrete_values() -> None:
    assert anchor_points(20, ComponentAnchor.STRONG) == 15
    assert anchor_points(15, ComponentAnchor.PARTIAL) == 8
    assert anchor_points(10, ComponentAnchor.ADJACENT) == 3
    assert anchor_points(5, ComponentAnchor.CLOSE) == 5


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
