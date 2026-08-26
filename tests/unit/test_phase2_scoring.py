import pytest

from job_search_cockpit.phase2.assessment_types import MatchScoreComponents


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
