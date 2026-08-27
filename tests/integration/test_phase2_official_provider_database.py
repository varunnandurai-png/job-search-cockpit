import sqlite3
from datetime import UTC, datetime
from hashlib import sha256
from types import SimpleNamespace

from job_search_cockpit.phase2.config import Phase2Settings
from job_search_cockpit.phase2.database import (
    create_phase2_engine,
    phase2_session_factory_for,
    upgrade_phase2_database,
)
from job_search_cockpit.phase2.discovery import DiscoveryService
from job_search_cockpit.phase2.models import Phase2ProviderInstanceApproval
from job_search_cockpit.phase2.types import Phase2ActivationView


def test_official_provider_instance_schema_is_append_only_and_has_no_secret_columns(
    phase2_settings: Phase2Settings,
) -> None:
    upgrade_phase2_database(f"sqlite:///{phase2_settings.database_path}")

    with sqlite3.connect(phase2_settings.database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(phase2_provider_instance_approvals)"
            )
        }
        triggers = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            )
        }

    assert {
        "phase2_provider_instance_approvals",
        "phase2_provider_instance_health_events",
    } <= tables
    assert "approval_fingerprint" in columns
    assert "content_types_json" in columns
    assert "source_identifier" in columns
    assert not columns & {"token", "key", "cookie", "authorization", "raw_html"}
    assert "prevent_phase2_provider_instance_approvals_update" in triggers
    assert "prevent_phase2_provider_instance_approvals_delete" in triggers


def test_official_instance_planner_uses_only_latest_enabled_current_approval(
    phase2_settings: Phase2Settings,
) -> None:
    upgrade_phase2_database(f"sqlite:///{phase2_settings.database_path}")
    engine = create_phase2_engine(phase2_settings)
    session_factory = phase2_session_factory_for(engine)
    with session_factory() as session, session.begin():
        session.add_all(
            [
                _approval("approval-a-enabled", "instance-a", True, 1, "2026-08-27T00:00:00"),
                _approval("approval-a-disabled", "instance-a", False, 1, "2026-08-27T01:00:00"),
                _approval("approval-b-enabled", "instance-b", True, 1, "2026-08-27T00:00:00"),
                _approval("approval-c-stale", "instance-c", True, 0, "2026-08-27T00:00:00"),
            ]
        )

    activation = SimpleNamespace(
        activation_view=lambda: Phase2ActivationView(
            state="active",
            reason="",
            activation_generation=1,
            revocation_generation=0,
            restore_generation=0,
            receipt_id="receipt-1",
            active_profile_version=1,
        )
    )
    coordinator = SimpleNamespace(_session_factory=session_factory)

    instances = DiscoveryService(
        phase2_settings, activation_service=activation, coordinator=coordinator
    )._approved_instances()

    assert [instance.instance_id for instance in instances] == ["instance-b"]
    engine.dispose()


def _approval(
    approval_id: str,
    instance_id: str,
    enabled: bool,
    activation_generation: int,
    created_at: str,
) -> Phase2ProviderInstanceApproval:
    return Phase2ProviderInstanceApproval(
        id=approval_id,
        instance_id=instance_id,
        provider_kind="greenhouse_public_board",
        employer_identity="Example Employer",
        hosts_json=["boards-api.greenhouse.io"],
        endpoint_url="https://boards-api.greenhouse.io/v1/boards/example/jobs?content=true",
        redirect_hosts_json=[],
        path_prefixes_json=["/v1/boards/example/jobs"],
        parser_version="greenhouse-public-v1",
        content_types_json=["application/json"],
        source_identifier="example",
        max_response_bytes=1_000_000,
        min_request_interval_seconds=30,
        enabled=enabled,
        actor="local-user",
        reason="approved boundary",
        phase2_activation_generation=activation_generation,
        phase2_restore_generation=0,
        approval_fingerprint=sha256(approval_id.encode()).hexdigest(),
        created_at=datetime.fromisoformat(created_at).replace(tzinfo=UTC),
    )
