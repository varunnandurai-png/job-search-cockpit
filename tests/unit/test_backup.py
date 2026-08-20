from hashlib import sha256
from pathlib import Path

from job_search_cockpit.storage.backup import create_safety_copy
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
