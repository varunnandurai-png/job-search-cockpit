from types import SimpleNamespace

from job_search_cockpit.phase2.assessment_types import GateResult
from job_search_cockpit.phase2.candidates import _review
from job_search_cockpit.search_profile.catalog import build_profile_v1


def test_review_accepts_provider_qualified_profile_location() -> None:
    revision = SimpleNamespace(
        id="eltropy-revision",
        public_description="Public job description",
        employer_name="Eltropy",
        locations_json=["Hyderabad, Telangana, India"],
        title="Senior Product Manager",
    )

    review = _review(revision, build_profile_v1(), current=True)

    assert review.gate_result is GateResult.PASS
    assert review.selected_location_path == "Hyderabad"


def test_review_keeps_location_selection_when_description_is_missing() -> None:
    revision = SimpleNamespace(
        id="missing-description",
        public_description="",
        employer_name="Eltropy",
        locations_json=["Hyderabad, Telangana, India"],
        title="Senior Product Manager",
    )

    review = _review(revision, build_profile_v1(), current=True)

    assert review.gate_result is GateResult.FAIL
    assert review.gate_reason_codes == ("missing_public_description",)
    assert review.selected_location_path == "Hyderabad"
