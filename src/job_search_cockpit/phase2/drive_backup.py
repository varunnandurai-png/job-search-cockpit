from dataclasses import dataclass
from datetime import datetime
from typing import Literal

DriveBackupStatus = Literal[
    "not_requested",
    "sign_in_required",
    "in_progress",
    "backed_up",
    "pending",
    "permission_expired",
]

_EVENT_KINDS = frozenset(
    {
        "requested",
        "authorization_required",
        "authorization_granted",
        "authorization_denied",
        "ids_reserved",
        "folder_verified",
        "file_verified",
        "pending",
        "permission_expired",
        "completed",
    }
)


@dataclass(frozen=True, slots=True)
class DriveBackupView:
    operation_id: str | None
    final_artifact_id: str
    status: DriveBackupStatus
    reason_code: str
    folder_id: str | None
    docx_file_id: str | None
    pdf_file_id: str | None
    docx_name: str | None
    docx_sha256: str | None
    pdf_name: str | None
    pdf_sha256: str | None
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class ReservedDriveIds:
    folder_id: str
    docx_file_id: str
    pdf_file_id: str


def derive_drive_backup_status(
    event_kinds: tuple[str, ...], *, active: bool
) -> DriveBackupStatus:
    """Fold bounded append-only events into a safe, user-visible state."""
    if any(kind not in _EVENT_KINDS for kind in event_kinds):
        raise ValueError("The Drive backup event history is invalid.")
    if not event_kinds:
        return "not_requested"
    if "completed" in event_kinds:
        return "backed_up"
    if "permission_expired" in event_kinds or "authorization_denied" in event_kinds:
        return "permission_expired"
    if "pending" in event_kinds:
        return "pending"
    if active:
        return "in_progress"
    if "authorization_required" in event_kinds:
        return "sign_in_required"
    return "pending"
