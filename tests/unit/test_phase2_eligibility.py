from job_search_cockpit.phase2.assessment_types import GateResult
from job_search_cockpit.phase2.eligibility import LocationGateInput, aggregate_location_paths


def test_one_passing_location_path_remains_eligible_when_another_path_fails() -> None:
    result = aggregate_location_paths(
        (
            LocationGateInput("bengaluru", GateResult.PASS),
            LocationGateInput("singapore", GateResult.FAIL),
        )
    )

    assert result.state is GateResult.PASS
    assert result.passing_location_ids == ("bengaluru",)


def test_all_unknown_location_paths_remain_unknown() -> None:
    result = aggregate_location_paths((LocationGateInput("hyderabad", GateResult.UNKNOWN),))

    assert result.state is GateResult.UNKNOWN
