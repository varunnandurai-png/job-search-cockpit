from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from job_search_cockpit.phase2.finalisation import FinalResumeArtifact
from job_search_cockpit.phase2.models import Phase2DriveBackupEvent, Phase2DriveBackupOperation
from job_search_cockpit.phase2.mutation import Phase2MutationCoordinator

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


@dataclass(frozen=True, slots=True)
class DriveBackupOperation:
    id: str
    final_artifact_id: str


class DriveBackupStore:
    """Persists only immutable, non-sensitive metadata for a private backup."""

    def __init__(self, coordinator: Phase2MutationCoordinator) -> None:
        self._coordinator = coordinator

    def create_operation(self, artifact: FinalResumeArtifact) -> DriveBackupOperation:
        def insert(session: Session) -> str:
            existing = session.scalar(
                select(Phase2DriveBackupOperation).where(
                    Phase2DriveBackupOperation.final_artifact_id == artifact.artifact_id
                )
            )
            if existing is not None:
                if not self._matches_artifact(existing, artifact):
                    raise ValueError("The final résumé artifact binding changed.")
                return existing.id
            operation = Phase2DriveBackupOperation(
                id=str(uuid4()),
                final_artifact_id=artifact.artifact_id,
                attempt_id=artifact.attempt_id,
                job_id=artifact.job_id,
                job_revision_id=artifact.job_revision_id,
                projection_fingerprint=artifact.content_fingerprint,
                content_fingerprint=artifact.content_fingerprint,
                requirement_ledger_fingerprint=artifact.authority.requirement_ledger_fingerprint,
                authorization_id=artifact.authority.authorization_id,
                authorization_nonce=artifact.authority.authorization_nonce,
                authorization_expires_at=artifact.authority.authorization_expires_at,
                phase1_profile_fingerprint=artifact.authority.phase1_profile_fingerprint,
                phase1_profile_generation=artifact.authority.phase1_profile_generation,
                phase1_readiness_fingerprint=artifact.authority.phase1_readiness_fingerprint,
                phase1_readiness_generation=artifact.authority.phase1_readiness_generation,
                phase1_authority_fingerprint=artifact.authority.phase1_authority_fingerprint,
                phase1_authority_generation=artifact.authority.phase1_authority_generation,
                phase1_restore_generation=artifact.authority.phase1_restore_generation,
                phase2_activation_generation=artifact.authority.phase2_activation_generation,
                phase2_restore_generation=artifact.authority.phase2_restore_generation,
                docx_name=artifact.docx_path.name,
                docx_sha256=artifact.docx_sha256,
                docx_byte_length=artifact.docx_byte_length,
                pdf_name=artifact.pdf_path.name,
                pdf_sha256=artifact.pdf_sha256,
                pdf_byte_length=artifact.pdf_byte_length,
            )
            session.add(operation)
            return operation.id

        operation_id = self._coordinator.run(insert, "record_private_drive_backup")
        return DriveBackupOperation(operation_id, artifact.artifact_id)

    def view_for_artifact(self, final_artifact_id: str) -> DriveBackupView:
        with self._coordinator._session_factory() as session:
            operation = session.scalar(
                select(Phase2DriveBackupOperation).where(
                    Phase2DriveBackupOperation.final_artifact_id == final_artifact_id
                )
            )
            if operation is None:
                return DriveBackupView(
                    operation_id=None,
                    final_artifact_id=final_artifact_id,
                    status="not_requested",
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
            events = tuple(
                session.scalars(
                    select(Phase2DriveBackupEvent)
                    .where(Phase2DriveBackupEvent.operation_id == operation.id)
                    .order_by(Phase2DriveBackupEvent.created_at, Phase2DriveBackupEvent.id)
                )
            )
            return DriveBackupView(
                operation_id=operation.id,
                final_artifact_id=operation.final_artifact_id,
                status=derive_drive_backup_status(
                    tuple(event.kind for event in events), active=False
                ),
                reason_code=(
                    events[-1].reason_code
                    if events and events[-1].reason_code
                    else "not_requested"
                ),
                folder_id=next(
                    (
                        event.folder_id
                        for event in reversed(events)
                        if event.folder_id is not None
                    ),
                    None,
                ),
                docx_file_id=self._file_id(events, "docx"),
                pdf_file_id=self._file_id(events, "pdf"),
                docx_name=operation.docx_name,
                docx_sha256=operation.docx_sha256,
                pdf_name=operation.pdf_name,
                pdf_sha256=operation.pdf_sha256,
                completed_at=next(
                    (
                        event.created_at
                        for event in reversed(events)
                        if event.kind == "completed"
                    ),
                    None,
                ),
            )

    def append_event(
        self,
        operation_id: str,
        kind: str,
        *,
        reason_code: str | None = None,
        file_kind: Literal["docx", "pdf"] | None = None,
        folder_id: str | None = None,
        file_id: str | None = None,
        remote_name: str | None = None,
        remote_mime_type: str | None = None,
        remote_sha256: str | None = None,
        remote_byte_length: int | None = None,
    ) -> None:
        self._validate_event_fields(
            kind,
            reason_code=reason_code,
            file_kind=file_kind,
            folder_id=folder_id,
            file_id=file_id,
            remote_name=remote_name,
            remote_mime_type=remote_mime_type,
            remote_sha256=remote_sha256,
            remote_byte_length=remote_byte_length,
        )

        def insert(session: Session) -> None:
            if session.get(Phase2DriveBackupOperation, operation_id) is None:
                raise ValueError("The Drive backup operation is unavailable.")
            events = tuple(
                session.scalars(
                    select(Phase2DriveBackupEvent)
                    .where(Phase2DriveBackupEvent.operation_id == operation_id)
                    .order_by(Phase2DriveBackupEvent.created_at, Phase2DriveBackupEvent.id)
                )
            )
            self._assert_event_order(events, kind, file_kind=file_kind)
            session.add(
                Phase2DriveBackupEvent(
                    id=str(uuid4()),
                    operation_id=operation_id,
                    kind=kind,
                    reason_code=reason_code,
                    file_kind=file_kind,
                    folder_id=folder_id,
                    file_id=file_id,
                    remote_name=remote_name,
                    remote_mime_type=remote_mime_type,
                    remote_sha256=remote_sha256,
                    remote_byte_length=remote_byte_length,
                )
            )

        self._coordinator.run(insert, "record_private_drive_backup_event")

    @staticmethod
    def _validate_event_fields(
        kind: str,
        *,
        reason_code: str | None,
        file_kind: str | None,
        folder_id: str | None,
        file_id: str | None,
        remote_name: str | None,
        remote_mime_type: str | None,
        remote_sha256: str | None,
        remote_byte_length: int | None,
    ) -> None:
        if kind not in _EVENT_KINDS:
            raise ValueError("The Drive backup event kind is invalid.")
        for value, limit in (
            (reason_code, 64),
            (folder_id, 255),
            (file_id, 255),
            (remote_name, 260),
            (remote_mime_type, 120),
            (remote_sha256, 64),
        ):
            if value is not None and not 1 <= len(value) <= limit:
                raise ValueError("The Drive backup event value is invalid.")
        if file_kind is not None and file_kind not in {"docx", "pdf"}:
            raise ValueError("The Drive backup file kind is invalid.")
        if remote_byte_length is not None and remote_byte_length < 0:
            raise ValueError("The Drive backup file size is invalid.")
        if kind == "file_verified" and (file_kind is None or file_id is None):
            raise ValueError("A verified Drive file requires its kind and ID.")

    @staticmethod
    def _assert_event_order(
        events: tuple[Phase2DriveBackupEvent, ...], kind: str, *, file_kind: str | None
    ) -> None:
        kinds = tuple(event.kind for event in events)
        if not kinds:
            if kind != "requested":
                raise ValueError("A Drive backup must be requested first.")
            return
        if "completed" in kinds:
            raise ValueError("The Drive backup operation is already complete.")
        if kind == "requested":
            raise ValueError("A Drive backup can only be requested once.")
        if kind in {"authorization_granted", "authorization_denied"} and (
            "authorization_required" not in kinds
        ):
            raise ValueError("Drive authorization was not requested.")
        if kind == "ids_reserved" and "authorization_granted" not in kinds:
            raise ValueError("Drive authorization was not granted.")
        if kind == "folder_verified" and "ids_reserved" not in kinds:
            raise ValueError("Drive IDs have not been reserved.")
        if kind == "file_verified":
            if "folder_verified" not in kinds:
                raise ValueError("The Drive folder has not been verified.")
            if any(
                event.file_kind == file_kind for event in events if event.kind == "file_verified"
            ):
                raise ValueError("That Drive file was already verified.")
        if kind == "completed":
            verified = {event.file_kind for event in events if event.kind == "file_verified"}
            if verified != {"docx", "pdf"}:
                raise ValueError("Both final résumé files must be verified first.")

    @staticmethod
    def _file_id(events: tuple[Phase2DriveBackupEvent, ...], kind: str) -> str | None:
        return next(
            (
                event.file_id
                for event in reversed(events)
                if event.file_kind == kind and event.file_id is not None
            ),
            None,
        )

    @staticmethod
    def _matches_artifact(
        operation: Phase2DriveBackupOperation, artifact: FinalResumeArtifact
    ) -> bool:
        return (
            operation.attempt_id == artifact.attempt_id
            and operation.job_id == artifact.job_id
            and operation.job_revision_id == artifact.job_revision_id
            and operation.content_fingerprint == artifact.content_fingerprint
            and operation.requirement_ledger_fingerprint
            == artifact.authority.requirement_ledger_fingerprint
            and operation.authorization_id == artifact.authority.authorization_id
            and operation.authorization_nonce == artifact.authority.authorization_nonce
            and operation.authorization_expires_at == artifact.authority.authorization_expires_at
            and operation.docx_name == artifact.docx_path.name
            and operation.docx_sha256 == artifact.docx_sha256
            and operation.docx_byte_length == artifact.docx_byte_length
            and operation.pdf_name == artifact.pdf_path.name
            and operation.pdf_sha256 == artifact.pdf_sha256
            and operation.pdf_byte_length == artifact.pdf_byte_length
        )


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
