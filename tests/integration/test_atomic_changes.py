import os
import threading
from pathlib import Path

import pytest

from job_search_cockpit.config import Settings
from job_search_cockpit.storage.database import create_engine_for, upgrade_database
from job_search_cockpit.storage.mutation import AppInstanceLock, MutationCoordinator
from tests.support.database import count_rows, failing_operation


def test_consistent_read_blocks_mutation_until_snapshot_finishes(tmp_path: Path) -> None:
    settings = Settings.for_tests(tmp_path / "data", tmp_path / "sources")
    upgrade_database(f"sqlite:///{settings.database_path}")
    lock = AppInstanceLock.acquire(settings)
    engine = create_engine_for(settings)
    coordinator = MutationCoordinator(settings, engine, lock)
    mutation_entered = threading.Event()
    mutation_finished = threading.Event()

    def mutate() -> None:
        mutation_entered.set()
        coordinator.run(lambda session: None, "concurrent_mutation", expected_version=None)
        mutation_finished.set()

    try:
        with coordinator.consistent_read():
            worker = threading.Thread(target=mutate)
            worker.start()
            assert mutation_entered.wait(timeout=1)
            assert not mutation_finished.wait(timeout=0.1)
        worker.join(timeout=2)
        assert mutation_finished.is_set()
    finally:
        coordinator.dispose()
        lock.release()


def test_coordinator_rolls_back_when_operation_fails(tmp_path: Path) -> None:
    settings = Settings.for_tests(tmp_path / "data", tmp_path / "sources")
    upgrade_database(f"sqlite:///{settings.database_path}")
    lock = AppInstanceLock.acquire(settings)
    engine = create_engine_for(settings)
    coordinator = MutationCoordinator(settings, engine, lock)
    try:
        with pytest.raises(RuntimeError, match="simulated failure"):
            coordinator.run(failing_operation, "import", expected_version=None)
        assert count_rows(settings.database_path, "claims") == 0
        assert len(tuple(settings.backup_dir.glob("*.sqlite3"))) == 1
        entries = coordinator.recovery_ledger.read_all()
        assert len(entries) == 1
        event = entries[0].event
        assert event.event_type == "backup_created"
        assert event.payload["reason"] == "import"
        assert event.payload["actor"] == "system"
        assert len(str(event.payload["sha256"])) == 64
    finally:
        engine.dispose()
        lock.release()


def test_vault_files_are_owner_only_under_permissive_umask(tmp_path: Path) -> None:
    settings = Settings.for_tests(tmp_path / "data", tmp_path / "sources")
    previous_umask = os.umask(0)
    try:
        engine = create_engine_for(settings)
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE permission_fixture (id INTEGER)")
            connection.exec_driver_sql("INSERT INTO permission_fixture VALUES (1)")
        protected_files = [
            settings.database_path,
            Path(f"{settings.database_path}-wal"),
            Path(f"{settings.database_path}-shm"),
        ]
        assert all(path.stat().st_mode & 0o777 == 0o600 for path in protected_files)
    finally:
        engine.dispose()
        os.umask(previous_umask)
