import errno
import fcntl
import os
import secrets
import shutil
import sqlite3
import threading
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import TypeVar
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from job_search_cockpit.config import Settings
from job_search_cockpit.storage.backup import BackupResult, create_safety_copy
from job_search_cockpit.storage.database import (
    create_engine_for,
    session_factory_for,
    upgrade_database,
)
from job_search_cockpit.storage.models import ImportAttempt, Phase1AuthorityState
from job_search_cockpit.storage.recovery_ledger import LedgerEntry, RecoveryEvent, RecoveryLedger
from job_search_cockpit.storage.restore import InvalidBackup, RestoreResult, verify_backup

T = TypeVar("T")


class VaultAlreadyOpen(RuntimeError):
    """Raised when another process owns the vault's lifetime lock."""


class MutationUnavailable(RuntimeError):
    """Raised when a coordinator no longer owns a usable lock."""


class AppInstanceLock:
    def __init__(self, path: Path, descriptor: int) -> None:
        self.path = path
        self._descriptor = descriptor
        self._held = True

    @classmethod
    def acquire(cls, settings: Settings) -> "AppInstanceLock":
        settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        settings.data_dir.chmod(0o700)
        path = settings.data_dir / "cockpit.lock"
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        path.chmod(0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            os.close(descriptor)
            if error.errno in (errno.EACCES, errno.EAGAIN):
                raise VaultAlreadyOpen("The Job Search Cockpit is already open.") from error
            raise
        return cls(path, descriptor)

    @property
    def held(self) -> bool:
        return self._held

    def release(self) -> None:
        if not self._held:
            return
        fcntl.flock(self._descriptor, fcntl.LOCK_UN)
        os.close(self._descriptor)
        self._held = False


def _verify_prepared_copy(path: Path) -> str:
    with sqlite3.connect(path) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    if integrity is None or integrity[0] != "ok" or revision is None:
        raise InvalidBackup("The prepared restore copy is invalid.")
    return sha256(path.read_bytes()).hexdigest()


class MutationCoordinator:
    def __init__(self, settings: Settings, engine: Engine, instance_lock: AppInstanceLock) -> None:
        if not instance_lock.held:
            raise MutationUnavailable("The application instance lock is not held.")
        self.settings = settings
        self.engine = engine
        self._session_factory: sessionmaker[Session] = session_factory_for(engine)
        self._instance_lock = instance_lock
        self._mutex = threading.RLock()
        self._request_condition = threading.Condition()
        self._active_requests = 0
        self._maintenance = False
        self._disposed = False
        self.recovery_ledger = RecoveryLedger(settings.data_dir / "recovery.jsonl")

    def _assert_available(self) -> None:
        if self._disposed or not self._instance_lock.held:
            raise MutationUnavailable("Vault mutations are not available.")

    def _create_recorded_backup(self, reason: str, actor: str) -> BackupResult:
        backup = create_safety_copy(
            self.settings.database_path,
            self.settings.backup_dir,
            reason,
        )
        self.recovery_ledger.append(
            RecoveryEvent(
                event_id=str(uuid4()),
                event_type="backup_created",
                payload={
                    "backup_id": backup.backup_id,
                    "vault_id": backup.vault_id,
                    "sha256": backup.sha256,
                    "alembic_revision": backup.alembic_revision,
                    "actor": actor,
                    "reason": reason,
                },
                created_at=backup.created_at,
            )
        )
        return backup

    @staticmethod
    def _touch_phase1_authority(session: Session, *, restored: bool = False) -> None:
        state = session.get(Phase1AuthorityState, 1)
        if state is None:
            state = Phase1AuthorityState(id=1)
            session.add(state)
            session.flush()
        state.authority_high_water_mark += 1
        state.readiness_generation += 1
        if restored:
            state.restore_generation += 1

    def run(
        self,
        operation: Callable[[Session], T],
        reason: str,
        expected_version: int | None,
    ) -> T:
        del expected_version
        with self._mutex:
            self._assert_available()
            self._create_recorded_backup(reason, actor="system")
            with self._session_factory() as session, session.begin():
                result = operation(session)
                self._touch_phase1_authority(session)
                return result

    def begin_request(self) -> None:
        """Enter a request that must finish before vault replacement."""
        with self._request_condition:
            while self._maintenance:
                self._request_condition.wait()
            self._assert_available()
            self._active_requests += 1

    def end_request(self) -> None:
        with self._request_condition:
            if self._active_requests <= 0:
                raise MutationUnavailable("The active request count is invalid.")
            self._active_requests -= 1
            if self._active_requests == 0:
                self._request_condition.notify_all()

    def _begin_maintenance(self) -> None:
        with self._request_condition:
            self._assert_available()
            self._maintenance = True
            while self._active_requests:
                self._request_condition.wait()

    def _end_maintenance(self) -> None:
        with self._request_condition:
            self._maintenance = False
            self._request_condition.notify_all()

    def _checkpoint_and_dispose(self) -> None:
        with self.engine.connect() as connection:
            checkpoint = connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)").one()
        if int(checkpoint[0]) != 0:
            raise MutationUnavailable("The vault is busy; restore was not started.")
        self.engine.dispose()

    def _replace_active_database(self, prepared: Path, rollback: BackupResult) -> None:
        self._checkpoint_and_dispose()
        for suffix in ("-wal", "-shm"):
            Path(f"{self.settings.database_path}{suffix}").unlink(missing_ok=True)
        try:
            os.replace(prepared, self.settings.database_path)
            self.settings.database_path.chmod(0o600)
            self.engine = create_engine_for(self.settings)
            self._session_factory = session_factory_for(self.engine)
            with self.engine.connect() as connection:
                if connection.exec_driver_sql("PRAGMA integrity_check").scalar_one() != "ok":
                    raise InvalidBackup("The restored vault failed its final integrity check.")
        except Exception:
            self.engine.dispose()
            for suffix in ("-wal", "-shm"):
                Path(f"{self.settings.database_path}{suffix}").unlink(missing_ok=True)
            rollback_copy = self.settings.data_dir / f".rollback-{secrets.token_hex(6)}.sqlite3"
            shutil.copyfile(rollback.path, rollback_copy)
            rollback_copy.chmod(0o600)
            os.replace(rollback_copy, self.settings.database_path)
            self.engine = create_engine_for(self.settings)
            self._session_factory = session_factory_for(self.engine)
            raise

    def restore(self, backup_id: str, actor: str, reason: str) -> RestoreResult:
        self._begin_maintenance()
        try:
            with self._mutex:
                self._assert_available()
                backup = verify_backup(self.settings.backup_dir, backup_id)
                prepared = self.settings.data_dir / f".restore-{secrets.token_hex(8)}.sqlite3"
                shutil.copyfile(backup.path, prepared)
                prepared.chmod(0o600)
                try:
                    upgrade_database(f"sqlite:///{prepared}")
                    restored_checksum = _verify_prepared_copy(prepared)
                    pre_restore = self._create_recorded_backup("before_restore", actor)
                    self._replace_active_database(prepared, pre_restore)
                    with self._session_factory() as session, session.begin():
                        self._touch_phase1_authority(session, restored=True)
                finally:
                    prepared.unlink(missing_ok=True)
                self.recovery_ledger.append(
                    RecoveryEvent(
                        event_id=str(uuid4()),
                        event_type="restore_completed",
                        payload={
                            "restore_id": str(uuid4()),
                            "backup_id": backup.backup_id,
                            "pre_restore_backup_id": pre_restore.backup_id,
                            "old_vault_id": pre_restore.vault_id,
                            "new_vault_id": backup.vault_id,
                            "old_checksum": pre_restore.sha256,
                            "new_checksum": restored_checksum,
                            "actor": actor,
                            "reason": reason,
                        },
                        created_at=datetime.now(UTC),
                    )
                )
                return RestoreResult(backup.backup_id, pre_restore.backup_id, restored_checksum)
        finally:
            self._end_maintenance()

    def install_prepared_database(self, prepared: Path, reason: str) -> str:
        """Atomically install a verified migrated copy while retaining rollback state."""
        with self._mutex:
            self._assert_available()
            checksum = _verify_prepared_copy(prepared)
            rollback = self._create_recorded_backup(reason, actor="system")
            self._replace_active_database(prepared, rollback)
            return checksum

    def reconcile_import_attempt_events(self, entries: Sequence[LedgerEntry]) -> int:
        relevant = [entry.event for entry in entries if entry.event.event_type == "import_attempt"]
        if not relevant:
            return 0
        event_ids = [event.event_id for event in relevant]
        with self._session_factory() as session:
            existing_before_backup = set(
                session.scalars(select(ImportAttempt.id).where(ImportAttempt.id.in_(event_ids)))
            )
        relevant = [event for event in relevant if event.event_id not in existing_before_backup]
        if not relevant:
            return 0

        def reconcile(session: Session) -> int:
            event_ids = [event.event_id for event in relevant]
            existing = set(
                session.scalars(select(ImportAttempt.id).where(ImportAttempt.id.in_(event_ids)))
            )
            created = 0
            for event in relevant:
                if event.event_id in existing:
                    continue
                payload = event.payload
                statuses = payload["source_statuses"]
                if not isinstance(statuses, dict):
                    raise ValueError("Recovery source statuses are invalid.")
                session.add(
                    ImportAttempt(
                        id=event.event_id,
                        preview_id=str(payload["preview_id"]),
                        candidate_digest=str(payload["candidate_digest"]),
                        manifest_version=str(payload["manifest_version"]),
                        outcome=str(payload["outcome"]),
                        source_statuses_json=statuses,
                        failure_class=str(payload.get("failure_class", "")) or None,
                        redacted_message=str(payload.get("redacted_message", "")) or None,
                        session_fingerprint=str(payload["session_fingerprint"]),
                        created_at=event.created_at,
                    )
                )
                created += 1
            return created

        return self.run(reconcile, "reconcile_import_attempts", expected_version=None)

    def dispose(self) -> None:
        with self._mutex:
            self.engine.dispose()
            self._disposed = True
