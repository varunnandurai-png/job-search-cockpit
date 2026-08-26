"""Add append-only Phase III resume finalisation metadata.

Revision ID: 0007_resume_finalisation
Revises: 0006_provider_discovery
Create Date: 2026-08-26
"""

from collections.abc import Sequence

from alembic import op
from job_search_cockpit.phase2.models import (
    Phase2FinalResumeArtifact,
    Phase2ResumeDocumentAttempt,
    Phase2ResumeDocumentAttemptEvent,
    Phase2ResumeRequirementLedger,
)

revision: str = "0007_resume_finalisation"
down_revision: str | None = "0006_provider_discovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    Phase2ResumeRequirementLedger.__table__,
    Phase2ResumeDocumentAttempt.__table__,
    Phase2ResumeDocumentAttemptEvent.__table__,
    Phase2FinalResumeArtifact.__table__,
)


def upgrade() -> None:
    for table in _TABLES:
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
    # Resume-finalisation audit history is intentionally irreversible.
    pass
