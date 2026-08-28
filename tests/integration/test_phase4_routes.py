from job_search_cockpit.phase2.drive_backup import DriveBackupView
from job_search_cockpit.phase2.runtime import Phase2Runtime
from job_search_cockpit.ports import PreparedVault
from tests.integration.test_phase3_routes import SyntheticRouteFinalisationService
from tests.support.web import authenticated_test_app, build_test_app


class SyntheticConfiguredDriveService:
    status = "not_requested"

    def view_for_artifact(self, artifact_id: str) -> DriveBackupView:
        return DriveBackupView(
            operation_id="operation-1" if self.status == "pending" else None,
            final_artifact_id=artifact_id,
            status=self.status,
            reason_code="not_requested",
            folder_id=None,
            docx_file_id=None,
            pdf_file_id=None,
            docx_name=None,
            docx_sha256=None,
            pdf_name=None,
            pdf_sha256=None,
            completed_at=None,
        )


def _configured_final_artifact(tmp_path, *, status="not_requested"):
    finalisation = SyntheticRouteFinalisationService(tmp_path, finalised=True)

    def configure(prepared: PreparedVault) -> None:
        runtime = prepared.phase2_runtime
        assert isinstance(runtime, Phase2Runtime)
        runtime.resume_finalisation_service = finalisation  # type: ignore[assignment]
        drive_service = SyntheticConfiguredDriveService()
        drive_service.status = status
        runtime.drive_backup_service = drive_service  # type: ignore[assignment]

    return configure


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


def test_verified_artifact_shows_the_visible_drive_backup_action(vault_settings, tmp_path) -> None:
    with authenticated_test_app(
        vault_settings, configure_prepared=_configured_final_artifact(tmp_path)
    ) as client:
        response = client.get("/phase-2/resume-reviews/attempt-1")

    assert "Back up to Google Drive" in response.text
    assert 'name="final_artifact_id" value="final-artifact-1"' in response.text


def test_pending_backup_shows_only_the_manual_retry_action(vault_settings, tmp_path) -> None:
    with authenticated_test_app(
        vault_settings, configure_prepared=_configured_final_artifact(tmp_path, status="pending")
    ) as client:
        response = client.get("/phase-2/resume-reviews/attempt-1")

    assert "Retry backup" in response.text
    assert "Back up to Google Drive" not in response.text
