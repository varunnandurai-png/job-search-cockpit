from datetime import UTC, datetime
from pathlib import Path

import pytest

from job_search_cockpit.storage.recovery_ledger import (
    InvalidRecoveryLedger,
    RecoveryEvent,
    RecoveryLedger,
)


def test_recovery_ledger_is_append_only_and_hash_chained(tmp_path: Path) -> None:
    ledger = RecoveryLedger(tmp_path / "recovery.jsonl")
    first = ledger.append(
        RecoveryEvent("event-1", "backup_created", {"backup_id": "backup-1"}, datetime.now(UTC))
    )
    second = ledger.append(
        RecoveryEvent("event-2", "restore_completed", {"backup_id": "backup-1"}, datetime.now(UTC))
    )
    events = ledger.read_all()
    assert len(events) == 2
    assert second.previous_hash == first.event_hash
    assert ledger.path.stat().st_mode & 0o777 == 0o600


def test_recovery_ledger_detects_tampering(tmp_path: Path) -> None:
    ledger = RecoveryLedger(tmp_path / "recovery.jsonl")
    ledger.append(
        RecoveryEvent("event-1", "backup_created", {"backup_id": "backup-1"}, datetime.now(UTC))
    )
    ledger.path.write_text(
        ledger.path.read_text(encoding="utf-8").replace("backup-1", "backup-X"),
        encoding="utf-8",
    )
    with pytest.raises(InvalidRecoveryLedger):
        ledger.read_all()
