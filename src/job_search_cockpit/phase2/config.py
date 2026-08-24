from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Phase2Settings:
    """Private paths owned exclusively by the Phase II catalog."""

    data_dir: Path

    @property
    def database_path(self) -> Path:
        return self.data_dir / "job_catalog.sqlite3"

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "job-catalog-backups"

    @property
    def lock_path(self) -> Path:
        return self.data_dir / "job-catalog.lock"

    @property
    def recovery_ledger_path(self) -> Path:
        return self.data_dir / "job-catalog-recovery.jsonl"
