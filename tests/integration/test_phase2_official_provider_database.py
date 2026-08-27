import sqlite3

from job_search_cockpit.phase2.config import Phase2Settings
from job_search_cockpit.phase2.database import upgrade_phase2_database


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
    assert not columns & {"token", "key", "cookie", "authorization", "raw_html"}
    assert "prevent_phase2_provider_instance_approvals_update" in triggers
    assert "prevent_phase2_provider_instance_approvals_delete" in triggers
