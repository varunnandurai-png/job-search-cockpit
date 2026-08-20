import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, Response

from job_search_cockpit.audit.service import AuditService
from job_search_cockpit.storage.database import session_factory_for
from job_search_cockpit.storage.models import AuditEvent
from job_search_cockpit.storage.mutation import MutationCoordinator
from job_search_cockpit.storage.recovery_ledger import LedgerEntry

router = APIRouter(prefix="/history")

REDACTED = "Confidential value hidden"


@dataclass(frozen=True, slots=True)
class HistoryRow:
    id: str
    event_type: str
    area: str
    summary: str
    source_label: str
    created_at: datetime
    sensitive: bool
    origin: str


def _coordinator(request: Request) -> MutationCoordinator:
    coordinator = request.app.state.prepared.coordinator
    if not isinstance(coordinator, MutationCoordinator):
        raise RuntimeError("Mutation coordinator is unavailable.")
    return coordinator


def _ledger_rows(coordinator: MutationCoordinator) -> tuple[HistoryRow, ...]:
    return tuple(
        HistoryRow(
            entry.event.event_id,
            entry.event.event_type,
            "recovery",
            entry.event.event_type.replace("_", " ").title(),
            "External recovery ledger",
            entry.event.created_at,
            False,
            "recovery",
        )
        for entry in coordinator.recovery_ledger.read_all()
    )


def _audit_row(event: AuditEvent) -> HistoryRow:
    return HistoryRow(
        event.id,
        event.event_type,
        event.area,
        event.summary,
        event.source_label,
        event.created_at,
        event.sensitive,
        "audit",
    )


@router.get("")
def show_history(request: Request) -> Response:
    coordinator = _coordinator(request)
    factory = session_factory_for(coordinator.engine)
    with factory() as session:
        rows = [_audit_row(event) for event in AuditService(session).list()]
    rows.extend(_ledger_rows(coordinator))
    rows.sort(key=lambda row: row.created_at.replace(tzinfo=None), reverse=True)
    response: Response = request.app.state.templates.TemplateResponse(
        request, "history.html", {"rows": rows, "redacted": REDACTED}
    )
    return response


def _safe_json(value: dict[str, object] | None) -> str:
    return json.dumps(value, indent=2, sort_keys=True) if value is not None else "Not recorded"


def _ledger_entry(entries: tuple[LedgerEntry, ...], event_id: str) -> LedgerEntry | None:
    return next((entry for entry in entries if entry.event.event_id == event_id), None)


@router.get("/{event_id}")
def show_history_event(request: Request, event_id: str) -> Response:
    coordinator = _coordinator(request)
    factory = session_factory_for(coordinator.engine)
    with factory() as session:
        event = AuditService(session).get(event_id)
        if event is not None:
            detail: dict[str, Any] = {
                "id": event.id,
                "event_type": event.event_type,
                "area": event.area,
                "summary": event.summary,
                "created_at": event.created_at,
                "source_label": event.source_label or "Not recorded",
                "reason": event.reason or "Not recorded",
                "supersedes": event.supersedes_event_id or "None",
                "before": REDACTED if event.sensitive else _safe_json(event.before_json),
                "after": REDACTED if event.sensitive else _safe_json(event.after_json),
                "sensitive": event.sensitive,
                "origin": "Vault audit history",
            }
        else:
            entry = _ledger_entry(coordinator.recovery_ledger.read_all(), event_id)
            if entry is None:
                return PlainTextResponse("History event not found.", status_code=404)
            detail = {
                "id": entry.event.event_id,
                "event_type": entry.event.event_type,
                "area": "recovery",
                "summary": entry.event.event_type.replace("_", " ").title(),
                "created_at": entry.event.created_at,
                "source_label": "External recovery ledger",
                "reason": str(entry.event.payload.get("reason", "Not recorded")),
                "supersedes": "None",
                "before": "Not recorded",
                "after": _safe_json(entry.event.payload),
                "sensitive": False,
                "origin": f"Recovery chain after {entry.previous_hash[:12]}",
            }
    response: Response = request.app.state.templates.TemplateResponse(
        request, "history_event.html", {"event": detail, "redacted": REDACTED}
    )
    return response
