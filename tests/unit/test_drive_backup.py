import pytest

from job_search_cockpit.phase2.drive_backup import (
    DriveBackupStore,
    FinalResumeDriveBackupService,
    ReservedDriveIds,
    derive_drive_backup_status,
)
from job_search_cockpit.phase2.finalisation import FINALISE_CONFIRMATION, FinaliseResumeCommand
from tests.support.phase3 import build_synthetic_phase3_runtime


class _AuthorizationWithAccess:
    def access_token(self, before_request):
        before_request()
        return "synthetic-access"


class _DriveThatRecordsVerifiedWork:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def generate_ids(self, access_token, count, *, before_request):
        assert access_token == "synthetic-access"
        assert count == 3
        before_request()
        self.calls.append("generate_ids")
        return ("folder-1", "docx-1", "pdf-1")

    def create_or_verify_folder(self, access_token, folder_id, *, before_request):
        assert access_token == "synthetic-access"
        assert folder_id == "folder-1"
        before_request()
        self.calls.append("folder")

    def upload_verified_file(
        self, *, access_token, file_id, folder_id, final_artifact_id, file_kind, before_request
    ):
        assert access_token == "synthetic-access"
        assert file_id == {"docx": "docx-1", "pdf": "pdf-1"}[file_kind]
        assert folder_id == "folder-1"
        assert final_artifact_id
        before_request()
        self.calls.append(file_kind)
        return type(
            "Metadata",
            (),
            {
                "id": file_id,
                "name": f"synthetic.{file_kind}",
                "mime_type": "application/octet-stream",
                "sha256": "a" * 64,
                "size": 1,
            },
        )()


@pytest.mark.parametrize(
    ("events", "active", "expected"),
    [
        (("requested", "authorization_required"), False, "sign_in_required"),
        (("requested",), True, "in_progress"),
        (("requested", "pending"), False, "pending"),
        (("requested", "authorization_denied"), False, "permission_expired"),
        (("requested", "permission_expired"), False, "permission_expired"),
        (("requested", "completed"), False, "backed_up"),
    ],
)
def test_status_is_derived_from_append_only_events(
    events: tuple[str, ...], active: bool, expected: str
) -> None:
    assert derive_drive_backup_status(events, active=active) == expected


def test_store_creates_one_operation_for_one_verified_artifact(tmp_path) -> None:
    runtime = build_synthetic_phase3_runtime(tmp_path)
    try:
        review = runtime.service.start_review("job-1")
        artifact = runtime.service.finalise(
            FinaliseResumeCommand(
                review.attempt_id,
                FINALISE_CONFIRMATION,
                runtime.headshot_path,
            )
        )
        store = DriveBackupStore(runtime.coordinator)

        first = store.create_operation(artifact)
        second = store.create_operation(artifact)

        assert second.id == first.id
        assert store.view_for_artifact(artifact.artifact_id).status == "not_requested"
    finally:
        runtime.close()


def test_store_rejects_a_file_result_before_backup_is_requested(tmp_path) -> None:
    runtime = build_synthetic_phase3_runtime(tmp_path)
    try:
        review = runtime.service.start_review("job-1")
        artifact = runtime.service.finalise(
            FinaliseResumeCommand(
                review.attempt_id,
                FINALISE_CONFIRMATION,
                runtime.headshot_path,
            )
        )
        store = DriveBackupStore(runtime.coordinator)
        operation = store.create_operation(artifact)

        with pytest.raises(ValueError, match="requested"):
            store.append_event(
                operation.id,
                "file_verified",
                file_kind="docx",
                file_id="remote-docx-id",
            )
    finally:
        runtime.close()


def test_store_round_trips_all_reserved_ids_for_manual_retry(tmp_path) -> None:
    runtime = build_synthetic_phase3_runtime(tmp_path)
    try:
        review = runtime.service.start_review("job-1")
        artifact = runtime.service.finalise(
            FinaliseResumeCommand(
                review.attempt_id,
                FINALISE_CONFIRMATION,
                runtime.headshot_path,
            )
        )
        store = DriveBackupStore(runtime.coordinator)
        operation = store.create_operation(artifact)
        store.append_event(operation.id, "requested")
        store.append_event(operation.id, "authorization_required")
        store.append_event(operation.id, "authorization_granted")

        store.append_event(
            operation.id,
            "ids_reserved",
            folder_id="folder-1",
            docx_file_id="docx-1",
            pdf_file_id="pdf-1",
        )

        assert store.reserved_ids(operation.id) == ReservedDriveIds(
            folder_id="folder-1",
            docx_file_id="docx-1",
            pdf_file_id="pdf-1",
        )
    finally:
        runtime.close()


def test_visible_request_with_existing_permission_backs_up_the_verified_pair(tmp_path) -> None:
    runtime = build_synthetic_phase3_runtime(tmp_path)
    try:
        review = runtime.service.start_review("job-1")
        artifact = runtime.service.finalise(
            FinaliseResumeCommand(
                review.attempt_id,
                FINALISE_CONFIRMATION,
                runtime.headshot_path,
            )
        )
        store = DriveBackupStore(runtime.coordinator)
        drive = _DriveThatRecordsVerifiedWork()
        service = FinalResumeDriveBackupService(
            finalisation_service=runtime.service,
            authorization_service=_AuthorizationWithAccess(),
            drive_client=drive,
            store=store,
        )

        result = service.request_backup(
            final_artifact_id=artifact.artifact_id,
            session_id="session-1",
            redirect_uri="http://127.0.0.1:8765/phase-2/drive-backups/oauth/callback",
        )

        assert result.authorization_url is None
        assert result.view.status == "backed_up"
        assert drive.calls == ["generate_ids", "folder", "docx", "pdf"]
        assert store.view_for_artifact(artifact.artifact_id).status == "backed_up"
    finally:
        runtime.close()
