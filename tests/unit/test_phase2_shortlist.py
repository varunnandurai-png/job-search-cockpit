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
