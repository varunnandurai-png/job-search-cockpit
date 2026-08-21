import threading
from pathlib import Path

import pytest
from sqlalchemy import text

from job_search_cockpit.config import Settings
from job_search_cockpit.storage.backup import create_safety_copy
from job_search_cockpit.storage.database import create_engine_for, upgrade_database
from job_search_cockpit.storage.mutation import AppInstanceLock, MutationCoordinator
from job_search_cockpit.storage.restore import InvalidBackup
from tests.support.database import count_rows


def test_restore_replaces_vault_and_preserves_pre_restore_copy(tmp_path: Path) -> None:
    settings = Settings.for_tests(tmp_path / "data", tmp_path / "sources")
    upgrade_database(f"sqlite:///{settings.database_path}")
    backup = create_safety_copy(settings.database_path, settings.backup_dir, "known_good")
    engine = create_engine_for(settings)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO claims
                    (id, canonical_key, category, subject, status, sensitivity, stale, version)
                VALUES
                    ('claim-1', 'fixture.claim', 'fixture', 'Fixture', 'unresolved',
                     'normal', 0, 1)
                """
            )
        )
    lock = AppInstanceLock.acquire(settings)
    coordinator = MutationCoordinator(settings, engine, lock)
    try:
        result = coordinator.restore(backup.backup_id, actor="Varun", reason="test restore")
        assert count_rows(settings.database_path, "claims") == 0
        assert result.pre_restore_backup_id != backup.backup_id
        entries = coordinator.recovery_ledger.read_all()
        assert [entry.event.event_type for entry in entries] == [
            "backup_created",
            "restore_completed",
        ]
        assert entries[0].event.payload["backup_id"] == result.pre_restore_backup_id
        assert entries[0].event.payload["actor"] == "Varun"
        assert entries[1].event.payload["pre_restore_backup_id"] == (
            result.pre_restore_backup_id
        )
    finally:
        coordinator.dispose()
        lock.release()


def test_corrupt_backup_is_rejected_without_changing_active_vault(tmp_path: Path) -> None:
    settings = Settings.for_tests(tmp_path / "data", tmp_path / "sources")
    upgrade_database(f"sqlite:///{settings.database_path}")
    backup = create_safety_copy(settings.database_path, settings.backup_dir, "known_good")
    backup.path.write_bytes(b"not sqlite")
    engine = create_engine_for(settings)
    lock = AppInstanceLock.acquire(settings)
    coordinator = MutationCoordinator(settings, engine, lock)
    try:
        with pytest.raises(InvalidBackup):
            coordinator.restore(backup.backup_id, actor="Varun", reason="test restore")
        assert count_rows(settings.database_path, "alembic_version") == 1
    finally:
        coordinator.dispose()
        lock.release()


def test_restore_waits_for_active_request_to_drain(tmp_path: Path) -> None:
    settings = Settings.for_tests(tmp_path / "data", tmp_path / "sources")
    upgrade_database(f"sqlite:///{settings.database_path}")
    backup = create_safety_copy(settings.database_path, settings.backup_dir, "known_good")
    engine = create_engine_for(settings)
    lock = AppInstanceLock.acquire(settings)
    coordinator = MutationCoordinator(settings, engine, lock)
    failures: list[BaseException] = []

    def restore() -> None:
        try:
            coordinator.restore(backup.backup_id, actor="Varun", reason="drain fixture")
        except BaseException as error:
            failures.append(error)

    thread = threading.Thread(target=restore)
    try:
        coordinator.begin_request()
        try:
            thread.start()
            thread.join(timeout=0.1)
            assert thread.is_alive()
        finally:
            coordinator.end_request()
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert failures == []
    finally:
        if thread.is_alive():
            thread.join(timeout=5)
        coordinator.dispose()
        lock.release()
