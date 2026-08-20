from datetime import UTC, datetime
from uuid import uuid4

from job_search_cockpit.storage.database import create_engine_for, session_factory_for
from job_search_cockpit.storage.models import AuditEvent
from job_search_cockpit.storage.recovery_ledger import RecoveryEvent, RecoveryLedger
from tests.support.web import authenticated_test_app


def _add_event(settings, *, sensitive: bool) -> AuditEvent:
    engine = create_engine_for(settings)
    event = AuditEvent(
        id=str(uuid4()),
        event_type="fixture_event",
        area="facts",
        subject_id="fixture-subject",
        summary="Fixture history summary",
        before_json={"value": "private-before"},
        after_json={"value": "private-after"},
        sensitive=sensitive,
        reason="Fixture reason",
        source_label="Sanitized source",
    )
    with session_factory_for(engine)() as session, session.begin():
        session.add(event)
    return event


def test_history_list_and_detail_redact_confidential_values(vault_settings):
    with authenticated_test_app(vault_settings) as client:
        event = _add_event(vault_settings, sensitive=True)
        response = client.get("/history")
        assert response.status_code == 200
        assert event.summary in response.text
        assert "private-before" not in response.text
        assert "Confidential value hidden" in response.text

        detail = client.get(f"/history/{event.id}")
        assert detail.status_code == 200
        assert "private-after" not in detail.text
        assert "Fixture reason" not in detail.text
        assert "Sanitized source" not in detail.text
        assert "Confidential value hidden" in detail.text


def test_nonconfidential_detail_and_external_recovery_event_are_visible(vault_settings):
    with authenticated_test_app(vault_settings) as client:
        event = _add_event(vault_settings, sensitive=False)
        ledger = RecoveryLedger(vault_settings.data_dir / "recovery.jsonl")
        recovery = RecoveryEvent(
            event_id=str(uuid4()),
            event_type="restore_completed",
            payload={"backup_id": "sanitized-backup", "reason": "Fixture restore"},
            created_at=datetime.now(UTC),
        )
        ledger.append(recovery)

        page = client.get("/history")
        assert "Restore Completed" in page.text
        detail = client.get(f"/history/{event.id}")
        assert "private-before" in detail.text
        recovery_detail = client.get(f"/history/{recovery.event_id}")
        assert "sanitized-backup" in recovery_detail.text
        assert client.get("/history/unknown-event").status_code == 404
