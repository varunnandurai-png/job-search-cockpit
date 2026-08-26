import sqlite3

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
