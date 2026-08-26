import pytest

from job_search_cockpit.phase2.assessment import ComponentContribution, calculate_component_score
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
