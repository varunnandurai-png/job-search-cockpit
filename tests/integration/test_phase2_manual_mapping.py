import sqlite3

import pytest
from sqlalchemy import inspect

from job_search_cockpit.phase2.database import create_phase2_engine, upgrade_phase2_database


def test_local_manual_mapping_attempt_schema_is_append_only(phase2_settings) -> None:
    upgrade_phase2_database(f"sqlite:///{phase2_settings.database_path}")
    engine = create_phase2_engine(phase2_settings)
    try:
        tables = set(inspect(engine).get_table_names())
        mapping_tables = {
            "phase2_local_manual_mapping_attempts",
            "phase2_local_manual_mapping_attempt_events",
        }
        assert mapping_tables <= tables
        forbidden = {"wording", "safe_wording", "content", "secret", "token"}
        for table in mapping_tables:
            columns = {column["name"] for column in inspect(engine).get_columns(table)}
            assert not columns.intersection(forbidden)
        columns = {
            column["name"]
            for column in inspect(engine).get_columns("phase2_local_manual_mapping_attempts")
        }
        assert {"logical_payload_digest", "manifest_fingerprint", "nonce_sha256"} <= columns
    finally:
        engine.dispose()
    with sqlite3.connect(phase2_settings.database_path) as connection:
        for table in mapping_tables:
            triggers = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name = ?",
                    (table,),
                )
            }
            assert {f"prevent_{table}_update", f"prevent_{table}_delete"} <= triggers
        connection.execute(
            """
            INSERT INTO phase2_local_manual_mapping_attempts (
                id, attempt_id, nonce_sha256, phase1_authorization_id, job_revision_id,
                selected_location_path_fingerprint, coverage_ledger_fingerprint,
                manifest_fingerprint, logical_payload_digest, rubric_version,
                retrieval_configuration_version, interpreter_configuration_version,
                response_schema_version, expires_at, state, created_at,
                phase1_profile_fingerprint, phase1_profile_generation,
                phase1_readiness_fingerprint, phase1_readiness_generation,
                phase1_authority_fingerprint, phase1_authority_generation,
                phase1_restore_generation, phase2_activation_generation,
                phase2_restore_generation
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "attempt-row",
                "attempt-1",
                "a" * 64,
                "phase1-auth",
                "revision-1",
                "b" * 64,
                "c" * 64,
                "d" * 64,
                "e" * 64,
                "rubric-v1",
                "retrieval-v1",
                "local-manual-v1",
                "schema-v1",
                "2026-09-01T00:00:00+00:00",
                "authorized",
                "2026-08-31T00:00:00+00:00",
                "f" * 64,
                1,
                "1" * 64,
                1,
                "2" * 64,
                1,
                0,
                1,
                0,
            ),
        )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("UPDATE phase2_local_manual_mapping_attempts SET state = 'failed'")
