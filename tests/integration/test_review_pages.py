from sqlalchemy import select

from job_search_cockpit.storage.database import create_engine_for, session_factory_for
from job_search_cockpit.storage.models import Claim, ClaimRevision
from tests.support.web import authenticated_test_app


def _import(client) -> None:
    preview = client.post("/imports/preview")
    assert preview.status_code == 200
    response = client.post(
        "/imports/apply",
        data={"preview_id": preview.headers["x-preview-id"]},
        follow_redirects=False,
    )
    assert response.status_code == 303


def _claim(settings, canonical_key: str) -> Claim:
    engine = create_engine_for(settings)
    with session_factory_for(engine)() as session:
        claim = session.scalar(select(Claim).where(Claim.canonical_key == canonical_key))
        assert claim is not None
        session.expunge(claim)
        return claim


def test_review_queue_prioritizes_conflicts_and_offers_filters(vault_settings):
    with authenticated_test_app(vault_settings) as client:
        _import(client)
        response = client.get("/review")
        assert response.status_code == 200
        assert "Facts that need your attention" in response.text
        assert "Conflicts" in response.text
        assert "Numbers" in response.text
        assert response.text.index("Sources disagree") < response.text.index("Review required")


def test_conflict_page_shows_every_source_version(vault_settings):
    with authenticated_test_app(vault_settings) as client:
        _import(client)
        claim = _claim(vault_settings, "profile.product_years")
        response = client.get(f"/review/{claim.id}")
        assert response.status_code == 200
        assert "These sources disagree" in response.text
        engine = create_engine_for(vault_settings)
        with session_factory_for(engine)() as session:
            values = tuple(
                session.scalars(
                    select(ClaimRevision.display_value).where(ClaimRevision.claim_id == claim.id)
                )
            )
        assert len(values) >= 2
        assert all(value in response.text for value in values)
        assert "Select this version" in response.text
        assert "Approve fact" not in response.text


def test_stale_review_form_does_not_overwrite_newer_decision(vault_settings):
    with authenticated_test_app(vault_settings) as client:
        _import(client)
        claim = _claim(vault_settings, "policy.resume.keep-critical-text-parseable-by-ats-software")
        response = client.post(
            f"/review/{claim.id}/approve",
            data={
                "revision_id": claim.active_revision_id,
                "expected_version": claim.version - 1,
            },
        )
        assert response.status_code == 409
        assert "This fact changed in another action" in response.text


def test_approve_and_sensitivity_actions_use_post_redirect_get(vault_settings):
    with authenticated_test_app(vault_settings) as client:
        _import(client)
        claim = _claim(vault_settings, "policy.resume.keep-critical-text-parseable-by-ats-software")
        approved = client.post(
            f"/review/{claim.id}/approve",
            data={"revision_id": claim.active_revision_id, "expected_version": claim.version},
            follow_redirects=False,
        )
        assert approved.status_code == 303
        changed = _claim(vault_settings, claim.canonical_key)
        sensitivity = client.post(
            f"/review/{claim.id}/sensitivity",
            data={"sensitivity": "confidential", "expected_version": changed.version},
            follow_redirects=False,
        )
        assert sensitivity.status_code == 303
        page = client.get(f"/review/{claim.id}")
        assert "Exact permission is required for later resume use" in page.text


def test_correction_error_preserves_submitted_wording(vault_settings):
    with authenticated_test_app(vault_settings) as client:
        _import(client)
        claim = _claim(
            vault_settings,
            "policy.resume.report-honest-confidence-and-never-guarantee-an-ats-outcome",
        )
        response = client.post(
            f"/review/{claim.id}/correct",
            data={
                "display_value": "Exact revised fixture wording",
                "reason": "",
                "expected_version": claim.version,
            },
        )
        assert response.status_code == 422
        assert "Exact revised fixture wording" in response.text
        assert "reason" in response.text.lower()
