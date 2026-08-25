"""Add append-only final-artifact metadata.

Revision ID: 0005_final_artifact_metadata
Revises: 0004_application_draft_storage
Create Date: 2026-08-25
"""

from collections.abc import Sequence

from alembic import op
from job_search_cockpit.phase2.models import Phase2FinalArtifact

revision: str = "0005_final_artifact_metadata"
down_revision: str | None = "0004_application_draft_storage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    table = Phase2FinalArtifact.__table__
    table.create(bind=op.get_bind(), checkfirst=True)
    for operation in ("update", "delete"):
        op.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS prevent_{table.name}_{operation}
            BEFORE {operation.upper()} ON {table.name}
            BEGIN
                SELECT RAISE(ABORT, '{table.name} is append-only');
            END
            """
        )


def downgrade() -> None:
    # Local final-artifact history is intentionally irreversible.
    pass
