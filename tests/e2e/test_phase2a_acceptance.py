from tests.support.web import authenticated_test_app


def test_phase2a_is_fail_closed_and_has_no_live_provider_path(vault_settings) -> None:
    with authenticated_test_app(vault_settings) as client:
        page = client.get("/phase-2")

    assert page.status_code == 200
    assert "No job sources have been contacted" in page.text
    assert "providers are not approved" in page.text
    assert (
        "discovery, scoring, shortlists, documents, and applications remain disabled"
        in page.text
    )
