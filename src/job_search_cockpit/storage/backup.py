import json
import os
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4


class BackupError(RuntimeError):
    """Raised when a verified safety copy cannot be created."""


def copy_database_online(source_path: Path, destination_path: Path) -> None:
    """Copy a live SQLite database, including committed WAL content."""
    if destination_path.exists():
        raise BackupError("The database-copy destination already exists.")
    descriptor = os.open(destination_path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    try:
        source_uri = f"file:{source_path}?mode=ro"
        with (
            sqlite3.connect(source_uri, uri=True) as source,
            sqlite3.connect(destination_path) as destination,
        ):
            source.backup(destination, pages=128, sleep=0.01)
        destination_path.chmod(0o600)
    except Exception as error:
        destination_path.unlink(missing_ok=True)
        raise BackupError("The live database could not be copied safely.") from error


@dataclass(frozen=True, slots=True)
class BackupResult:
    backup_id: str
    path: Path
    manifest_path: Path
    sha256: str
    vault_id: str
    alembic_revision: str
    reason: str
    created_at: datetime


def _protected_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


def _write_owner_only(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
    finally:
        os.close(descriptor)
    os.replace(temporary, path)
    path.chmod(0o600)


def _vault_id(database_path: Path) -> str:
    identity_path = database_path.parent / "vault.identity"
    try:
        identity = identity_path.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        identity = str(uuid4())
        try:
            _write_owner_only(identity_path, f"{identity}\n".encode("ascii"))
        except FileExistsError:
            identity = identity_path.read_text(encoding="ascii").strip()
    if not identity:
        raise BackupError("The vault identity file is empty.")
    identity_path.chmod(0o600)
    return identity


def _database_metadata(path: Path) -> str:
    try:
        with sqlite3.connect(path) as connection:
            integrity_row = connection.execute("PRAGMA integrity_check").fetchone()
            revision_row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    except sqlite3.Error as error:
        raise BackupError("The safety copy could not be verified.") from error
    if integrity_row is None or integrity_row[0] != "ok":
        raise BackupError("The safety copy failed SQLite integrity verification.")
    if revision_row is None:
        raise BackupError("The safety copy has no schema revision.")
    return str(revision_row[0])


def _backup_manifest(result: BackupResult) -> dict[str, Any]:
    return {
        "backup_id": result.backup_id,
        "sha256": result.sha256,
        "vault_id": result.vault_id,
        "alembic_revision": result.alembic_revision,
        "reason": result.reason,
        "created_at": result.created_at.isoformat(),
        "database_file": result.path.name,
    }


def create_safety_copy(database_path: Path, backup_dir: Path, reason: str) -> BackupResult:
    if not database_path.is_file():
        raise BackupError("The active vault does not exist.")
    _protected_directory(database_path.parent)
    _protected_directory(backup_dir)
    created_at = datetime.now(UTC)
    backup_id = f"{created_at:%Y%m%dT%H%M%S.%fZ}-{secrets.token_hex(6)}"
    backup_path = backup_dir / f"{backup_id}.sqlite3"
    manifest_path = backup_dir / f"{backup_id}.json"

    try:
        copy_database_online(database_path, backup_path)
        alembic_revision = _database_metadata(backup_path)
        checksum = sha256(backup_path.read_bytes()).hexdigest()
        result = BackupResult(
            backup_id=backup_id,
            path=backup_path,
            manifest_path=manifest_path,
            sha256=checksum,
            vault_id=_vault_id(database_path),
            alembic_revision=alembic_revision,
            reason=reason,
            created_at=created_at,
        )
        manifest = json.dumps(_backup_manifest(result), sort_keys=True, separators=(",", ":"))
        _write_owner_only(manifest_path, f"{manifest}\n".encode())
        return result
    except Exception as error:
        backup_path.unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)
        if isinstance(error, BackupError):
            raise
        raise BackupError("The safety copy could not be created.") from error
