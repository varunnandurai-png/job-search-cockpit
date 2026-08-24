import sqlite3
import stat

import pytest

from job_search_cockpit.config import Settings
from job_search_cockpit.phase2.config import Phase2Settings
from job_search_cockpit.phase2.database import upgrade_phase2_database
from tests.support.database import sqlite_integrity


def test_phase2_database_is_separate_and_owner_only(phase2_settings: Phase2Settings) -> None:
    upgrade_phase2_database(f"sqlite:///{phase2_settings.database_path}")

    phase1_settings = Settings(data_dir=phase2_settings.data_dir)
    assert phase2_settings.database_path != phase1_settings.database_path
    assert stat.S_IMODE(phase2_settings.database_path.stat().st_mode) == 0o600
    assert sqlite_integrity(phase2_settings.database_path) == "ok"


def test_phase2_schema_has_no_phase1_tables(phase2_settings: Phase2Settings) -> None:
    upgrade_phase2_database(f"sqlite:///{phase2_settings.database_path}")

    with sqlite3.connect(phase2_settings.database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }

    assert "claims" not in tables
    assert {
        "phase2_authority_state",
        "phase2_activation_grants",
        "phase2_resume_preparation_attempts",
    } <= tables


def test_resume_preparation_attempt_metadata_is_append_only(
    phase2_settings: Phase2Settings,
) -> None:
    upgrade_phase2_database(f"sqlite:///{phase2_settings.database_path}")

    with sqlite3.connect(phase2_settings.database_path) as connection:
        connection.execute(
            """
            INSERT INTO phase2_resume_preparation_attempts (
                id, job_id, job_revision_id, authorization_id, authorization_expires_at,
                activation_generation, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "attempt-1",
                "sanitized-job-1",
                "sanitized-revision-1",
                "sanitized-authorization-1",
                "2026-08-24T09:15:00+00:00",
                1,
                "2026-08-24T09:00:00+00:00",
            ),
        )

        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE phase2_resume_preparation_attempts SET job_id = 'other' "
                "WHERE id = 'attempt-1'"
            )
