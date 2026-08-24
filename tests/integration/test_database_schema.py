from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from job_search_cockpit.config import Settings
from job_search_cockpit.storage.database import create_engine_for, upgrade_database

EXPECTED_TABLES = {
    "alembic_version",
    "source_documents",
    "source_occurrences",
    "import_runs",
    "import_run_sources",
    "import_run_occurrences",
    "import_attempts",
    "claims",
    "claim_revisions",
    "claim_evidence",
    "claim_support_assertions",
    "conflict_groups",
    "conflict_members",
    "conflict_resolutions",
    "decisions",
    "named_uses",
    "confidential_permission_events",
    "audit_events",
    "search_profile_versions",
    "phase1_authority_state",
    "phase1_acceptance_receipts",
}


def _database_url(path: Path) -> str:
    return f"sqlite:///{path}"


def test_initial_migration_creates_all_phase_1_tables(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path / "vault.sqlite3")
    upgrade_database(database_url)
    tables = set(inspect(create_engine(database_url)).get_table_names())
    assert tables == EXPECTED_TABLES


def test_migration_installs_update_and_delete_guards_for_immutable_tables(
    tmp_path: Path,
) -> None:
    database_url = _database_url(tmp_path / "vault.sqlite3")
    upgrade_database(database_url)
    engine = create_engine(database_url)
    with engine.connect() as connection:
        trigger_names = {
            row[0]
            for row in connection.execute(
                text("SELECT name FROM sqlite_master WHERE type = 'trigger'")
            )
        }
    immutable_tables = {
        "claim_revisions",
        "decisions",
        "audit_events",
        "conflict_resolutions",
        "import_runs",
        "import_attempts",
        "source_occurrences",
        "claim_support_assertions",
        "named_uses",
        "confidential_permission_events",
        "phase1_acceptance_receipts",
    }
    assert trigger_names == {
        f"prevent_{table}_{operation}"
        for table in immutable_tables
        for operation in ("update", "delete")
    } | {
        "prevent_search_profile_versions_delete",
        "prevent_search_profile_versions_history_update",
    }


def test_audit_history_rejects_raw_update_and_delete(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path / "vault.sqlite3")
    upgrade_database(database_url)
    engine = create_engine(database_url)
    now = datetime.now(UTC).isoformat()
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO audit_events
                    (id, event_type, area, subject_id, summary, sensitive, created_at)
                VALUES
                    ('event-1', 'test', 'facts', 'claim-1', 'Created', 0, :created_at)
                """
            ),
            {"created_at": now},
        )

    with pytest.raises(IntegrityError, match="append-only"), engine.begin() as connection:
        connection.execute(text("UPDATE audit_events SET summary = 'Changed' WHERE id = 'event-1'"))

    with pytest.raises(IntegrityError, match="append-only"), engine.begin() as connection:
        connection.execute(text("DELETE FROM audit_events WHERE id = 'event-1'"))


def test_claim_state_constraints_reject_unknown_values(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path / "vault.sqlite3")
    upgrade_database(database_url)
    engine = create_engine(database_url)
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            text(
                """
                    INSERT INTO claims
                        (id, canonical_key, category, subject, status, sensitivity, stale, version)
                    VALUES
                        ('claim-1', 'fixture.claim', 'fixture', 'Fixture', 'invented',
                         'normal', 0, 1)
                    """
            )
        )


def test_nullable_periods_do_not_bypass_revision_identity(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path / "vault.sqlite3")
    upgrade_database(database_url)
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO claims
                    (id, canonical_key, category, subject, status, sensitivity, stale, version)
                VALUES
                    ('claim-1', 'fixture.claim', 'fixture', 'Fixture', 'unresolved',
                     'normal', 0, 1)
                """
            )
        )
        values = {
            "claim_id": "claim-1",
            "value_json": '{"text": "same"}',
            "display_value": "Same",
            "semantic_value": "same",
            "origin": "source",
            "employer_key": "",
            "created_at": datetime.now(UTC).isoformat(),
        }
        connection.execute(
            text(
                """
                INSERT INTO claim_revisions
                    (id, claim_id, value_json, display_value, semantic_value, origin,
                     employer_key, period_start, period_end, created_at)
                VALUES
                    ('revision-1', :claim_id, :value_json, :display_value, :semantic_value,
                     :origin, :employer_key, NULL, NULL, :created_at)
                """
            ),
            values,
        )
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    """
                    INSERT INTO claim_revisions
                        (id, claim_id, value_json, display_value, semantic_value, origin,
                         employer_key, period_start, period_end, created_at)
                    VALUES
                        ('revision-2', :claim_id, :value_json, :display_value, :semantic_value,
                         :origin, :employer_key, NULL, NULL, :created_at)
                    """
                ),
                values,
            )


def test_engine_factory_enables_foreign_keys_and_wal(vault_settings: Settings) -> None:
    engine = create_engine_for(vault_settings)
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one() == "wal"
    finally:
        engine.dispose()
