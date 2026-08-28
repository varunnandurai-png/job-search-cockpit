import sqlite3

from job_search_cockpit.phase2.config import Phase2Settings
from job_search_cockpit.phase2.database import upgrade_phase2_database


def test_phase4_backup_metadata_is_append_only_and_excludes_sensitive_values(
    phase2_settings: Phase2Settings,
) -> None:
    upgrade_phase2_database(f"sqlite:///{phase2_settings.database_path}")

    tables = {
        "phase2_drive_backup_operations",
        "phase2_drive_backup_events",
    }
    forbidden_columns = {
        "body",
        "wording",
        "absolute_path",
        "token",
        "authorization_code",
        "cookie",
        "password",
        "secret",
        "raw_response",
        "session_url",
    }

    with sqlite3.connect(phase2_settings.database_path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0017_drive_reserved_file_ids",
        )
        available_tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert tables <= available_tables
        for table in tables:
            columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            assert not columns.intersection(forbidden_columns)
            trigger_names = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name = ?",
                    (table,),
                )
            }
            assert {f"prevent_{table}_update", f"prevent_{table}_delete"} <= trigger_names

        event_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(phase2_drive_backup_events)")
        }
        assert {"folder_id", "docx_file_id", "pdf_file_id"} <= event_columns
