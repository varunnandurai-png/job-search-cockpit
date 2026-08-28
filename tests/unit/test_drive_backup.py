import pytest

from job_search_cockpit.phase2.drive_backup import DriveBackupStore, derive_drive_backup_status
from job_search_cockpit.phase2.finalisation import FINALISE_CONFIRMATION, FinaliseResumeCommand
from tests.support.phase3 import build_synthetic_phase3_runtime


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
