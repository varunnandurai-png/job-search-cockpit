"""Add append-only Phase II résumé-preparation metadata.

Revision ID: 0002_resume_preparation_attempts
Revises: 0001_phase2_activation
Create Date: 2026-08-24
"""

from collections.abc import Sequence

from alembic import op
from job_search_cockpit.phase2.models import Phase2ResumePreparationAttempt

revision: str = "0002_resume_preparation_attempts"
down_revision: str | None = "0001_phase2_activation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    table = Phase2ResumePreparationAttempt.__table__
    table.create(bind=op.get_bind(), checkfirst=True)
    for operation in ("update", "delete"):
        op.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS prevent_phase2_resume_preparation_attempts_{operation}
            BEFORE {operation.upper()} ON phase2_resume_preparation_attempts
            BEGIN
                SELECT RAISE(ABORT, 'phase2_resume_preparation_attempts is append-only');
            END
            """
        )


def downgrade() -> None:
    for operation in ("update", "delete"):
        op.execute(
            f"DROP TRIGGER IF EXISTS prevent_phase2_resume_preparation_attempts_{operation}"
        )
    Phase2ResumePreparationAttempt.__table__.drop(bind=op.get_bind(), checkfirst=True)
