from tests.support.web import build_test_app


def test_oauth_callback_is_the_only_cookie_exception_and_rejects_unknown_state(
    vault_settings,
) -> None:
    with build_test_app(vault_settings) as (_launch, client):
        callback = client.get(
            "/phase-2/drive-backups/oauth/callback?state=wrong-state&code=wrong-code"
        )
        protected = client.get("/phase-2/resume-reviews/attempt-1")

    assert callback.status_code == 400
    assert "Launch session required" not in callback.text
    assert protected.status_code == 401
