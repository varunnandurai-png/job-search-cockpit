from sqlalchemy import inspect

from job_search_cockpit.phase2.database import create_phase2_engine, upgrade_phase2_database


def test_local_manual_mapping_attempt_schema_is_append_only(phase2_settings) -> None:
    upgrade_phase2_database(f"sqlite:///{phase2_settings.database_path}")
    engine = create_phase2_engine(phase2_settings)
    try:
        tables = set(inspect(engine).get_table_names())
        assert "phase2_local_manual_mapping_attempts" in tables
        assert "phase2_local_manual_mapping_attempt_events" in tables
        columns = {
            column["name"]
            for column in inspect(engine).get_columns("phase2_local_manual_mapping_attempts")
        }
        assert {"logical_payload_digest", "manifest_fingerprint", "nonce_sha256"} <= columns
    finally:
        engine.dispose()
