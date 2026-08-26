import sqlite3

import pytest

from job_search_cockpit.phase2.config import Phase2Settings
from job_search_cockpit.phase2.database import upgrade_phase2_database


def test_phase3_metadata_tables_are_append_only_and_hold_no_resume_body(
    phase2_settings: Phase2Settings,
) -> None:
    upgrade_phase2_database(f"sqlite:///{phase2_settings.database_path}")

    tables = {
        "phase2_resume_requirement_ledgers",
        "phase2_resume_document_attempts",
        "phase2_resume_document_attempt_events",
        "phase2_final_resume_artifacts",
    }
    forbidden = {
        "body",
        "wording",
        "content",
        "draft",
        "revision_file",
        "bytes",
        "token",
        "secret",
        "password",
        "cookie",
        "otp",
        "submission",
        "drive",
    }

    with sqlite3.connect(phase2_settings.database_path) as connection:
        available_tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert tables <= available_tables
        for table in tables:
            columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            assert not columns.intersection(forbidden)
            trigger_names = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name = ?",
                    (table,),
                )
            }
            assert {f"prevent_{table}_update", f"prevent_{table}_delete"} <= trigger_names


def test_phase3_migration_head_and_append_only_triggers_are_effective(
    phase2_settings: Phase2Settings,
) -> None:
    upgrade_phase2_database(f"sqlite:///{phase2_settings.database_path}")

    with sqlite3.connect(phase2_settings.database_path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0007_resume_finalisation",
        )
        connection.execute(
            """
            INSERT INTO phase2_resume_document_attempt_events
                (id, attempt_id, kind, reason_code, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "synthetic-event",
                "synthetic-attempt",
                "finalisation_failed",
                "bounded_reason",
                "2026-08-26T00:00:00+00:00",
            ),
        )

        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE phase2_resume_document_attempt_events SET reason_code = ? WHERE id = ?",
                ("changed", "synthetic-event"),
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "DELETE FROM phase2_resume_document_attempt_events WHERE id = ?",
                ("synthetic-event",),
            )


def test_phase3_artifacts_enforce_one_pair_per_review_attempt(
    phase2_settings: Phase2Settings,
) -> None:
    upgrade_phase2_database(f"sqlite:///{phase2_settings.database_path}")

    with sqlite3.connect(phase2_settings.database_path) as connection:
        unique_indexes = [
            row[1]
            for row in connection.execute(
                "PRAGMA index_list(phase2_final_resume_artifacts)"
            )
            if row[2]
        ]
        unique_column_sets = {
            tuple(
                index_row[2]
                for index_row in connection.execute(f"PRAGMA index_info({index_name})")
            )
            for index_name in unique_indexes
        }

    assert ("attempt_id",) in unique_column_sets
