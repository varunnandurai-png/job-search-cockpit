import sqlite3

import pytest

from job_search_cockpit.phase2.config import Phase2Settings
from job_search_cockpit.phase2.database import upgrade_phase2_database


def test_provider_discovery_schema_is_append_only_and_has_no_secret_columns(
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

    assert {
        "phase2_discovery_runs",
        "phase2_source_listing_observations",
        "phase2_job_records",
        "phase2_job_revisions",
        "phase2_job_verifications",
    } <= tables

    forbidden = {
        "token",
        "key",
        "cookie",
        "session",
        "password",
        "otp",
        "submission",
        "answer_wording",
    }
    for table in {
        "phase2_discovery_runs",
        "phase2_source_listing_observations",
        "phase2_job_records",
        "phase2_job_revisions",
        "phase2_job_verifications",
    }:
        columns = {
            row[1] for row in connection.execute(f"PRAGMA table_info({table})")
        }
        assert not columns.intersection(forbidden)


def test_provider_discovery_schema_has_immutable_fingerprint_keys_and_triggers(
    phase2_settings: Phase2Settings,
) -> None:
    upgrade_phase2_database(f"sqlite:///{phase2_settings.database_path}")

    with sqlite3.connect(phase2_settings.database_path) as connection:
        indexes = [
            row[1]
            for row in connection.execute(
                "PRAGMA index_list(phase2_source_listing_observations)"
            )
        ]
        revision_indexes = [
            row[1]
            for row in connection.execute("PRAGMA index_list(phase2_job_revisions)")
        ]
        source_index_columns = [
            {row[2] for row in connection.execute(f"PRAGMA index_info({index})")}
            for index in indexes
        ]
        revision_index_columns = [
            {row[2] for row in connection.execute(f"PRAGMA index_info({index})")}
            for index in revision_indexes
        ]
        triggers = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            )
        }
        foreign_keys = {
            row[2]
            for row in connection.execute(
                "PRAGMA foreign_key_list(phase2_job_verifications)"
            )
        }

    assert {"provider_id", "source_listing_id", "content_fingerprint"} in source_index_columns
    assert {"job_record_id", "content_fingerprint"} in revision_index_columns
    for table in {
        "phase2_discovery_runs",
        "phase2_source_listing_observations",
        "phase2_job_records",
        "phase2_job_revisions",
        "phase2_job_verifications",
    }:
        assert f"prevent_{table}_update" in triggers
        assert f"prevent_{table}_delete" in triggers
    assert foreign_keys == {"phase2_job_revisions"}


def test_provider_discovery_tables_reject_updates_and_deletes(
    phase2_settings: Phase2Settings,
) -> None:
    upgrade_phase2_database(f"sqlite:///{phase2_settings.database_path}")

    with sqlite3.connect(phase2_settings.database_path) as connection:
        connection.execute(
            """
            INSERT INTO phase2_discovery_runs (
                id, phase1_profile_fingerprint, phase1_profile_generation,
                phase1_readiness_fingerprint, phase1_readiness_generation,
                phase1_authority_fingerprint, phase1_authority_generation,
                phase1_restore_generation, phase2_activation_generation,
                phase2_restore_generation, created_at
            ) VALUES ('run-1', ?, 1, ?, 1, ?, 1, 0, 1, 0, ?)
            """,
            ("a" * 64, "b" * 64, "c" * 64, "2026-08-25T00:00:00+00:00"),
        )
        connection.execute(
            """
            INSERT INTO phase2_source_listing_observations (
                id, discovery_run_id, provider_id, source_listing_id,
                canonical_url, title, employer_name, locations_json,
                public_description, retrieved_at, raw_content_fingerprint,
                content_fingerprint, created_at
            ) VALUES ('observation-1', 'run-1', 'provider-1', 'listing-1',
                'https://example.test/jobs/1', 'Public title', 'Public employer',
                '[]', 'Public description', ?, ?, ?, ?)
            """,
            (
                "2026-08-25T00:00:00+00:00",
                "d" * 64,
                "e" * 64,
                "2026-08-25T00:00:00+00:00",
            ),
        )
        connection.execute(
            "INSERT INTO phase2_job_records VALUES ('job-1', ?, ?)",
            ("f" * 64, "2026-08-25T00:00:00+00:00"),
        )
        connection.execute(
            """
            INSERT INTO phase2_job_revisions (
                id, job_record_id, source_observation_id, canonical_url,
                title, employer_name, locations_json, public_description,
                content_fingerprint, created_at
            ) VALUES ('revision-1', 'job-1', 'observation-1',
                'https://example.test/jobs/1', 'Public title', 'Public employer',
                '[]', 'Public description', ?, ?)
            """,
            ("1" * 64, "2026-08-25T00:00:00+00:00"),
        )
        connection.execute(
            """
            INSERT INTO phase2_job_verifications (
                id, authorization_id, authorization_nonce, job_revision_id,
                selected_location_path_fingerprint, source_observation_fingerprint,
                phase1_profile_fingerprint, phase1_profile_generation,
                phase1_readiness_fingerprint, phase1_readiness_generation,
                phase1_authority_fingerprint, phase1_authority_generation,
                phase1_restore_generation, phase2_activation_generation,
                phase2_restore_generation, expires_at, created_at
            ) VALUES ('verification-1', 'authorization-1', 'nonce-1', 'revision-1',
                ?, ?, ?, 1, ?, 1, ?, 1, 0, 1, 0, ?, ?)
            """,
            (
                "2" * 64,
                "3" * 64,
                "4" * 64,
                "5" * 64,
                "6" * 64,
                "2026-08-25T01:00:00+00:00",
                "2026-08-25T00:00:00+00:00",
            ),
        )

        for table in (
            "phase2_discovery_runs",
            "phase2_source_listing_observations",
            "phase2_job_records",
            "phase2_job_revisions",
            "phase2_job_verifications",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                connection.execute(f"UPDATE {table} SET id = id")
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                connection.execute(f"DELETE FROM {table}")
