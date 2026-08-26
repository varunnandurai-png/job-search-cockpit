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
