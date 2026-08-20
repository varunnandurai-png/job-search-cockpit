import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any


class InvalidRecoveryLedger(RuntimeError):
    """Raised when recovery history fails its hash-chain validation."""


@dataclass(frozen=True, slots=True)
class RecoveryEvent:
    event_id: str
    event_type: str
    payload: dict[str, object]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class LedgerReceipt:
    event_id: str
    previous_hash: str
    event_hash: str


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    event: RecoveryEvent
    previous_hash: str
    event_hash: str


class RecoveryLedger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._mutex = threading.Lock()

    @staticmethod
    def _event_payload(event: RecoveryEvent, previous_hash: str) -> dict[str, Any]:
        return {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "payload": event.payload,
            "created_at": event.created_at.isoformat(),
            "previous_hash": previous_hash,
        }

    @staticmethod
    def _digest(payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return sha256(canonical).hexdigest()

    def read_all(self) -> tuple[LedgerEntry, ...]:
        if not self.path.exists():
            return ()
        previous_hash = "0" * 64
        entries: list[LedgerEntry] = []
        seen_ids: set[str] = set()
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
            for line in lines:
                stored = json.loads(line)
                event = RecoveryEvent(
                    event_id=str(stored["event_id"]),
                    event_type=str(stored["event_type"]),
                    payload=dict(stored["payload"]),
                    created_at=datetime.fromisoformat(stored["created_at"]),
                )
                payload = self._event_payload(event, previous_hash)
                expected_hash = self._digest(payload)
                if stored.get("previous_hash") != previous_hash:
                    raise InvalidRecoveryLedger("Recovery history chain is broken.")
                if stored.get("event_hash") != expected_hash:
                    raise InvalidRecoveryLedger("Recovery history was altered.")
                if event.event_id in seen_ids:
                    raise InvalidRecoveryLedger("Recovery history contains a duplicate event.")
                entries.append(LedgerEntry(event, previous_hash, expected_hash))
                seen_ids.add(event.event_id)
                previous_hash = expected_hash
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise InvalidRecoveryLedger("Recovery history is invalid.") from error
        return tuple(entries)

    def append(self, event: RecoveryEvent) -> LedgerReceipt:
        with self._mutex:
            entries = self.read_all()
            if any(entry.event.event_id == event.event_id for entry in entries):
                raise InvalidRecoveryLedger("Recovery event IDs cannot be reused.")
            previous_hash = entries[-1].event_hash if entries else "0" * 64
            payload = self._event_payload(event, previous_hash)
            event_hash = self._digest(payload)
            stored = {**payload, "event_hash": event_hash}
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.path.parent.chmod(0o700)
            descriptor = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                line = json.dumps(stored, sort_keys=True, separators=(",", ":"))
                os.write(descriptor, f"{line}\n".encode())
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            self.path.chmod(0o600)
            return LedgerReceipt(event.event_id, previous_hash, event_hash)

    def reconcile_import_attempts(self, coordinator: object) -> object:
        from job_search_cockpit.storage.mutation import MutationCoordinator

        if not isinstance(coordinator, MutationCoordinator):
            raise TypeError("A MutationCoordinator is required.")
        return coordinator.reconcile_import_attempt_events(self.read_all())
