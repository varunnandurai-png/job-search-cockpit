"""Create the Phase 1 fact vault.

Revision ID: 0001_phase_1_vault
Revises:
Create Date: 2026-08-19
"""

from collections.abc import Sequence

from alembic import op
from job_search_cockpit.storage.models import Base

revision: str = "0001_phase_1_vault"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

IMMUTABLE_TABLES = (
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
)


def _install_immutability_triggers() -> None:
    for table in IMMUTABLE_TABLES:
        for operation in ("update", "delete"):
            op.execute(
                f"""
                CREATE TRIGGER prevent_{table}_{operation}
                BEFORE {operation.upper()} ON {table}
                BEGIN
                    SELECT RAISE(ABORT, '{table} is append-only');
                END
                """
            )
    op.execute(
        """
        CREATE TRIGGER prevent_search_profile_versions_delete
        BEFORE DELETE ON search_profile_versions
        BEGIN
            SELECT RAISE(ABORT, 'search_profile_versions is append-only');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER prevent_search_profile_versions_history_update
        BEFORE UPDATE ON search_profile_versions
        WHEN NOT (
            OLD.active = 1 AND NEW.active = 0
            AND OLD.id = NEW.id
            AND OLD.version_number = NEW.version_number
            AND OLD.payload_json = NEW.payload_json
            AND OLD.reason = NEW.reason
            AND OLD.confirmation = NEW.confirmation
            AND OLD.diff_digest = NEW.diff_digest
            AND OLD.created_at = NEW.created_at
        )
        BEGIN
            SELECT RAISE(ABORT, 'search_profile_versions history is immutable');
        END
        """
    )


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())
    _install_immutability_triggers()


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS prevent_search_profile_versions_history_update")
    op.execute("DROP TRIGGER IF EXISTS prevent_search_profile_versions_delete")
    for table in IMMUTABLE_TABLES:
        for operation in ("update", "delete"):
            op.execute(f"DROP TRIGGER IF EXISTS prevent_{table}_{operation}")
    Base.metadata.drop_all(bind=op.get_bind())
