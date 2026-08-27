import sqlite3

from job_search_cockpit.phase2.config import Phase2Settings
from job_search_cockpit.phase2.database import upgrade_phase2_database


def test_match_assessment_schema_is_append_only_and_avoids_sensitive_text(
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
            row[1] for row in connection.execute("PRAGMA table_info(phase2_match_assessments)")
        }
        triggers = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            )
        }

    assert {
        "phase2_job_gate_assessments",
        "phase2_location_eligibility_paths",
        "phase2_match_assessments",
        "phase2_match_components",
        "phase2_requirement_mappings",
        "phase2_shortlist_decisions",
    } <= tables
    assert {"job_revision_id", "rubric_version", "total_score", "fact_set_fingerprint"} <= columns
    assert not {
        "public_description",
        "safe_wording",
        "token",
        "api_key",
        "resume_text",
    } & columns
    assert "prevent_phase2_match_assessments_update" in triggers
    assert "prevent_phase2_match_assessments_delete" in triggers


def test_assessment_metadata_binds_each_derived_record_to_current_authority_generations(
    phase2_settings: Phase2Settings,
) -> None:
    """A stale derived record must never be publishable as a current assessment."""
    upgrade_phase2_database(f"sqlite:///{phase2_settings.database_path}")
    derived_tables = {
        "phase2_job_gate_assessments",
        "phase2_location_eligibility_paths",
        "phase2_match_assessments",
        "phase2_match_components",
        "phase2_requirement_mappings",
        "phase2_shortlist_decisions",
    }
    required_fence_columns = {
        "phase1_profile_fingerprint",
        "phase1_profile_generation",
        "phase1_readiness_fingerprint",
        "phase1_readiness_generation",
        "phase1_authority_fingerprint",
        "phase1_authority_generation",
        "phase1_restore_generation",
        "phase2_activation_generation",
        "phase2_restore_generation",
    }

    with sqlite3.connect(phase2_settings.database_path) as connection:
        columns_by_table = {
            table: {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            for table in derived_tables
        }

    assert all(required_fence_columns <= columns for columns in columns_by_table.values())
