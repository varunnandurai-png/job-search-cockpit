import json

from job_search_cockpit.search_profile.catalog import MoneyFloor, build_profile_v1
from job_search_cockpit.search_profile.service import profile_diff_digest
from tests.support.web import authenticated_test_app


def test_search_profile_page_shows_locked_filters(vault_settings):
    with authenticated_test_app(vault_settings) as client:
        response = client.get("/search-profile")
        assert response.status_code == 200
        assert "Hyderabad" in response.text
        assert "₹46 LPA minimum" in response.text
        assert "JPMorganChase" in response.text
        assert "Senior Product Manager" in response.text
        assert "Version 1" in response.text
        assert "every future discovery run" in response.text
        assert 'action="/search-profile/preview"' in response.text
        assert 'id="diff-digest"' not in response.text


def test_profile_preview_computes_the_reviewed_diff_digest(vault_settings):
    old = build_profile_v1()
    new = old.model_copy(update={"notice_period_days": 30})
    expected_digest = profile_diff_digest(old, new)
    with authenticated_test_app(vault_settings) as client:
        response = client.post(
            "/search-profile/preview",
            data={
                "payload_json": new.model_dump_json(),
                "reason": "Notice period changed",
                "expected_active_version": 1,
            },
        )

        assert response.status_code == 200
        assert "Review the proposed change" in response.text
        assert "Current version" in response.text
        assert "Proposed version" in response.text
        assert f'name="expected_diff_digest" value="{expected_digest}"' in response.text
        assert 'name="reason" value="Notice period changed"' in response.text
        assert 'id="diff-digest"' not in response.text


def test_confirmed_profile_change_creates_visible_version(vault_settings):
    old = build_profile_v1()
    new = old.model_copy(update={"notice_period_days": 30})
    with authenticated_test_app(vault_settings) as client:
        response = client.post(
            "/search-profile/new-version",
            data={
                "payload_json": json.dumps(new.model_dump(mode="json")),
                "reason": "Notice period changed",
                "confirmation": "CREATE NEW SEARCH PROFILE VERSION",
                "expected_active_version": 1,
                "expected_diff_digest": profile_diff_digest(old, new),
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        page = client.get("/search-profile")
        assert "Version 2" in page.text
        assert "30 days" in page.text


def test_profile_page_renders_active_compensation_floors(vault_settings):
    old = build_profile_v1()
    floors = dict(old.compensation_floors)
    floors.update(
        {
            "Hyderabad": MoneyFloor("INR", 5_000_000, "annual_total"),
            "Bengaluru": MoneyFloor("INR", 5_500_000, "annual_total"),
        }
    )
    new = old.model_copy(update={"compensation_floors": floors})
    with authenticated_test_app(vault_settings) as client:
        client.post(
            "/search-profile/new-version",
            data={
                "payload_json": json.dumps(new.model_dump(mode="json")),
                "reason": "Compensation updated",
                "confirmation": "CREATE NEW SEARCH PROFILE VERSION",
                "expected_active_version": 1,
                "expected_diff_digest": profile_diff_digest(old, new),
            },
        )
        page = client.get("/search-profile")
        assert "₹50 LPA minimum" in page.text
        assert "₹55 LPA minimum" in page.text


def test_stale_profile_submission_is_rejected(vault_settings):
    profile = build_profile_v1()
    with authenticated_test_app(vault_settings) as client:
        response = client.post(
            "/search-profile/new-version",
            data={
                "payload_json": profile.model_dump_json(),
                "reason": "Stale fixture",
                "confirmation": "CREATE NEW SEARCH PROFILE VERSION",
                "expected_active_version": 0,
                "expected_diff_digest": profile_diff_digest(profile, profile),
            },
        )
        assert response.status_code == 409
        assert "active target profile changed" in response.text.lower()
