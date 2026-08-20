from job_search_cockpit.search_profile.catalog import MoneyFloor, build_profile_v1
from tests.support.builders import load_golden_profile_v1


def test_profile_v1_preserves_approved_hard_filters() -> None:
    profile = build_profile_v1()
    assert profile.locations == ("Hyderabad", "Bengaluru", "Singapore")
    assert profile.compensation_floors == {
        "Hyderabad": MoneyFloor("INR", 4_600_000, "annual_total"),
        "Bengaluru": MoneyFloor("INR", 4_800_000, "annual_total"),
        "Singapore": MoneyFloor("SGD", 120_000, "annual_base"),
    }
    assert profile.excluded_employers == ("JPMorganChase",)
    assert profile.notice_period_days == 60
    assert profile.location_allocation == {"Hyderabad": 40, "Bengaluru": 45, "Singapore": 15}
    assert profile.role_difficulty_allocation == {
        "direct_fit": 50,
        "stretch": 35,
        "aspirational": 15,
    }


def test_profile_v1_matches_every_field_in_golden_fixture() -> None:
    assert build_profile_v1().model_dump(mode="json") == load_golden_profile_v1()
