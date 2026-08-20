import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path


class InvalidBackup(RuntimeError):
    """Raised when a backup cannot be safely restored."""


@dataclass(frozen=True, slots=True)
class VerifiedBackup:
    backup_id: str
    path: Path
    manifest_path: Path
    sha256: str
    vault_id: str
    alembic_revision: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class RestoreResult:
    backup_id: str
    pre_restore_backup_id: str
    restored_sha256: str


def verify_backup(backup_dir: Path, backup_id: str) -> VerifiedBackup:
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-"
    if not backup_id or any(character not in allowed for character in backup_id):
        raise InvalidBackup("The backup identifier is invalid.")
    path = backup_dir / f"{backup_id}.sqlite3"
    manifest_path = backup_dir / f"{backup_id}.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        checksum = sha256(path.read_bytes()).hexdigest()
        if manifest["backup_id"] != backup_id or manifest["database_file"] != path.name:
            raise InvalidBackup("The backup manifest does not match the selected backup.")
        if manifest["sha256"] != checksum:
            raise InvalidBackup("The backup checksum does not match its manifest.")
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        if integrity is None or integrity[0] != "ok" or revision is None:
            raise InvalidBackup("The backup failed SQLite integrity or schema verification.")
        if revision[0] != manifest["alembic_revision"]:
            raise InvalidBackup("The backup schema does not match its manifest.")
        return VerifiedBackup(
            backup_id=backup_id,
            path=path,
            manifest_path=manifest_path,
            sha256=checksum,
            vault_id=str(manifest["vault_id"]),
            alembic_revision=str(revision[0]),
            created_at=datetime.fromisoformat(manifest["created_at"]),
        )
    except InvalidBackup:
        raise
    except (OSError, KeyError, TypeError, ValueError, sqlite3.Error, json.JSONDecodeError) as error:
        raise InvalidBackup("The backup could not be verified.") from error
