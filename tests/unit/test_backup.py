import sqlite3
from hashlib import sha256
from pathlib import Path

from job_search_cockpit.storage.backup import copy_database_online, create_safety_copy
from tests.support.database import migrated_wal_vault, sqlite_integrity


def test_safety_copy_has_timestamp_hash_and_reason(tmp_path: Path) -> None:
    source = migrated_wal_vault(tmp_path)
    result = create_safety_copy(source, tmp_path / "backups", "before_review")
    assert result.path.exists()
    assert result.manifest_path.exists()
    assert result.sha256 == sha256(result.path.read_bytes()).hexdigest()
    assert result.reason == "before_review"
    assert sqlite_integrity(result.path) == "ok"
    assert result.path.stat().st_mode & 0o777 == 0o600
    assert result.manifest_path.stat().st_mode & 0o777 == 0o600


def test_two_backups_created_at_same_time_have_unique_names(tmp_path: Path) -> None:
    source = migrated_wal_vault(tmp_path)
    first = create_safety_copy(source, tmp_path / "backups", "first")
    second = create_safety_copy(source, tmp_path / "backups", "second")
    assert first.backup_id != second.backup_id
    assert first.path != second.path


def test_online_copy_includes_committed_wal_content(tmp_path: Path) -> None:
    source = migrated_wal_vault(tmp_path)
    destination = tmp_path / "prepared.sqlite3"
    with sqlite3.connect(source) as writer:
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("CREATE TABLE wal_fixture (value TEXT NOT NULL)")
        writer.execute("INSERT INTO wal_fixture VALUES ('committed-in-wal')")
        writer.commit()
        assert Path(f"{source}-wal").exists()
        copy_database_online(source, destination)

    with sqlite3.connect(destination) as copied:
        row = copied.execute("SELECT value FROM wal_fixture").fetchone()
    assert row == ("committed-in-wal",)
