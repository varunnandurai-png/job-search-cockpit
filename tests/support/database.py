import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def count_rows(database_path: Path, table: str) -> int:
    if not table.replace("_", "").isalnum():
        raise ValueError("Unsafe table name")
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()
    assert row is not None
    return int(row[0])


def failing_operation(_session: object) -> None:
    raise RuntimeError("simulated failure")


def sqlite_integrity(database_path: Path) -> str:
    with sqlite3.connect(database_path) as connection:
        row = connection.execute("PRAGMA integrity_check").fetchone()
    assert row is not None
    return str(row[0])


def migrated_wal_vault(tmp_path: Path) -> Path:
    database_path = tmp_path / "vault.sqlite3"
    module = __import__("job_search_cockpit.storage.database", fromlist=["upgrade_database"])
    upgrade = module.upgrade_database
    upgrade(f"sqlite:///{database_path}")
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
    return database_path


@contextmanager
def running_instance_lock(settings: object) -> Iterator[object]:
    module = __import__("job_search_cockpit.storage.mutation", fromlist=["AppInstanceLock"])
    lock_type = module.AppInstanceLock
    lock = lock_type.acquire(settings)
    try:
        yield lock
    finally:
        lock.release()


class VaultHarness:
    """Thin test adapter; domain services remain the real implementation."""

    def __init__(self, **operations: Callable[..., Any]) -> None:
        self._operations = operations

    def __getattr__(self, name: str) -> Callable[..., Any]:
        try:
            return self._operations[name]
        except KeyError as error:
            raise AttributeError(name) from error
