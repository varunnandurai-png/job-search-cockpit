import errno
import fcntl
import os
import secrets
import shutil
import sqlite3
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import TypeVar
from uuid import uuid4

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from job_search_cockpit.phase2.config import Phase2Settings
from job_search_cockpit.phase2.database import (
    create_phase2_engine,
    phase2_session_factory_for,
    upgrade_phase2_database,
)
from job_search_cockpit.phase2.models import Phase2AuthorityState
from job_search_cockpit.phase2.recovery_ledger import RecoveryEvent, RecoveryLedger
from job_search_cockpit.storage.backup import BackupResult, create_safety_copy
from job_search_cockpit.storage.restore import InvalidBackup, RestoreResult, verify_backup

T = TypeVar("T")


class Phase2AlreadyOpen(RuntimeError):
    """Raised when another process owns the Phase II catalog lock."""


class Phase2MutationUnavailable(RuntimeError):
    """Raised when the isolated Phase II catalog is unavailable."""


class Phase2InstanceLock:
    def __init__(self, path: Path, descriptor: int) -> None:
        self.path = path
        self._descriptor = descriptor
        self._held = True

    @classmethod
    def acquire(cls, settings: Phase2Settings) -> "Phase2InstanceLock":
        settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        settings.data_dir.chmod(0o700)
        descriptor = os.open(settings.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        settings.lock_path.chmod(0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            os.close(descriptor)
            if error.errno in (errno.EACCES, errno.EAGAIN):
                raise Phase2AlreadyOpen("The Phase II catalog is already open.") from error
            raise
        return cls(settings.lock_path, descriptor)

    @property
    def held(self) -> bool:
        return self._held

    def release(self) -> None:
        if not self._held:
            return
        fcntl.flock(self._descriptor, fcntl.LOCK_UN)
        os.close(self._descriptor)
        self._held = False


class Phase2MutationCoordinator:
    def __init__(
        self, settings: Phase2Settings, engine: Engine, instance_lock: Phase2InstanceLock
    ) -> None:
        if not instance_lock.held:
            raise Phase2MutationUnavailable("The Phase II catalog lock is not held.")
        self.settings = settings
        self.engine = engine
        self._instance_lock = instance_lock
        self._session_factory: sessionmaker[Session] = phase2_session_factory_for(engine)
        self._mutex = threading.RLock()
        self._disposed = False
        self.recovery_ledger = RecoveryLedger(settings.recovery_ledger_path)

    def _assert_available(self) -> None:
        if self._disposed or not self._instance_lock.held:
            raise Phase2MutationUnavailable("Phase II mutations are unavailable.")

    def _create_recorded_backup(self, reason: str, actor: str) -> BackupResult:
        backup = create_safety_copy(
            self.settings.database_path,
            self.settings.backup_dir,
            reason,
            identity_filename="job-catalog.identity",
        )
        self.recovery_ledger.append(
            RecoveryEvent(
                event_id=str(uuid4()),
                event_type="phase2_backup_created",
                payload={
                    "backup_id": backup.backup_id,
                    "catalog_id": backup.vault_id,
                    "sha256": backup.sha256,
                    "alembic_revision": backup.alembic_revision,
                    "actor": actor,
                    "reason": reason,
                },
                created_at=backup.created_at,
            )
        )
        return backup

    def run(self, operation: Callable[[Session], T], reason: str, *, actor: str = "system") -> T:
        with self._mutex:
            self._assert_available()
            self._create_recorded_backup(reason, actor)
            with self._session_factory() as session, session.begin():
                return operation(session)

    def restore(self, backup_id: str, actor: str, reason: str) -> RestoreResult:
        with self._mutex:
            self._assert_available()
            backup = verify_backup(self.settings.backup_dir, backup_id)
            prepared = self.settings.data_dir / f".phase2-restore-{secrets.token_hex(8)}.sqlite3"
            shutil.copyfile(backup.path, prepared)
            prepared.chmod(0o600)
            try:
                upgrade_phase2_database(f"sqlite:///{prepared}")
                with sqlite3.connect(prepared) as connection:
                    integrity = connection.execute("PRAGMA integrity_check").fetchone()
                if integrity is None or integrity[0] != "ok":
                    raise InvalidBackup(
                        "The restored Phase II catalog failed integrity verification."
                    )
                checksum = sha256(prepared.read_bytes()).hexdigest()
                pre_restore = self._create_recorded_backup("before_phase2_restore", actor)
                self.engine.dispose()
                for suffix in ("-wal", "-shm"):
                    Path(f"{self.settings.database_path}{suffix}").unlink(missing_ok=True)
                os.replace(prepared, self.settings.database_path)
                self.settings.database_path.chmod(0o600)
                self.engine = create_phase2_engine(self.settings)
                self._session_factory = phase2_session_factory_for(self.engine)
                with self._session_factory() as session, session.begin():
                    state = session.get(Phase2AuthorityState, 1)
                    if state is None:
                        raise Phase2MutationUnavailable(
                            "The Phase II authority state is unavailable."
                        )
                    state.restore_generation += 1
                    state.revocation_generation += 1
                self.recovery_ledger.append(
                    RecoveryEvent(
                        event_id=str(uuid4()),
                        event_type="phase2_restore_completed",
                        payload={
                            "backup_id": backup.backup_id,
                            "pre_restore_backup_id": pre_restore.backup_id,
                            "actor": actor,
                            "reason": reason,
                        },
                        created_at=datetime.now(UTC),
                    )
                )
                return RestoreResult(backup.backup_id, pre_restore.backup_id, checksum)
            finally:
                prepared.unlink(missing_ok=True)

    def dispose(self) -> None:
        with self._mutex:
            self.engine.dispose()
            self._disposed = True
