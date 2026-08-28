import pytest

from job_search_cockpit.phase2.drive_backup import derive_drive_backup_status


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
