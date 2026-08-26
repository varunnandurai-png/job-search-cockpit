from datetime import UTC, datetime

from job_search_cockpit.phase2.assessment_types import ConfidenceState
from job_search_cockpit.phase2.shortlist import ShortlistCandidate, focused_shortlist


def test_focused_shortlist_is_capped_and_deterministically_orders_by_score_then_id() -> None:
    candidates = tuple(
        ShortlistCandidate(assessment_id=f"assessment-{index:02d}", score=80)
        for index in range(25)
    )

    shortlist = focused_shortlist(candidates)

    assert len(shortlist) == 20
    assert shortlist[0].assessment_id == "assessment-00"
    assert shortlist[-1].assessment_id == "assessment-19"


def test_focused_shortlist_rejects_a_high_score_with_an_unresolved_hard_gate() -> None:
    shortlist = focused_shortlist(
        (
            ShortlistCandidate("blocked", 95, hard_gates_pass=False),
            ShortlistCandidate("qualified", 70),
        )
    )

    assert tuple(candidate.assessment_id for candidate in shortlist) == ("qualified",)


def test_focused_shortlist_orders_equal_scores_by_higher_confidence() -> None:
    shortlist = focused_shortlist(
        (
            ShortlistCandidate("medium", 80, confidence=ConfidenceState.MEDIUM),
            ShortlistCandidate("high", 80, confidence=ConfidenceState.HIGH),
        )
    )

    assert tuple(candidate.assessment_id for candidate in shortlist) == ("high", "medium")


def test_focused_shortlist_orders_equal_score_and_confidence_by_official_freshness() -> None:
    shortlist = focused_shortlist(
        (
            ShortlistCandidate(
                "older", 80, official_verified_at=datetime(2026, 8, 1, tzinfo=UTC)
            ),
            ShortlistCandidate(
                "newer", 80, official_verified_at=datetime(2026, 8, 2, tzinfo=UTC)
            ),
        )
    )

    assert tuple(candidate.assessment_id for candidate in shortlist) == ("newer", "older")
