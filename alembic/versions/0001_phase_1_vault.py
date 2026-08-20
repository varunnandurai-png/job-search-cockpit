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


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())
    _install_immutability_triggers()


def downgrade() -> None:
    for table in IMMUTABLE_TABLES:
        for operation in ("update", "delete"):
            op.execute(f"DROP TRIGGER IF EXISTS prevent_{table}_{operation}")
    Base.metadata.drop_all(bind=op.get_bind())
