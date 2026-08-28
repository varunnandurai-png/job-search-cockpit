from tests.support.web import authenticated_test_app, build_test_app


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


def test_backup_request_requires_an_enabled_service_and_opaque_artifact_id(vault_settings) -> None:
    with authenticated_test_app(vault_settings) as client:
        response = client.post(
            "/phase-2/drive-backups",
            data={"final_artifact_id": "not-a-path"},
            follow_redirects=False,
        )

    assert response.status_code == 400
    assert "Drive backup is unavailable" in response.text
