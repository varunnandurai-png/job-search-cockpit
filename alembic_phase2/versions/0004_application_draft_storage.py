"""Add append-only reusable-answer and no-submit draft metadata.

Revision ID: 0004_application_draft_storage
Revises: 0003_resume_preparation_bindings
Create Date: 2026-08-24
"""

from collections.abc import Sequence

from alembic import op
from job_search_cockpit.phase2.models import (
    Phase2ApplicationDraft,
    Phase2ApplicationDraftAnswer,
    Phase2ApplicationDraftReviewFlag,
    Phase2ReusableAnswer,
)

revision: str = "0004_application_draft_storage"
down_revision: str | None = "0003_resume_preparation_bindings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    Phase2ReusableAnswer.__table__,
    Phase2ApplicationDraft.__table__,
    Phase2ApplicationDraftAnswer.__table__,
    Phase2ApplicationDraftReviewFlag.__table__,
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
    # Local preparation history is intentionally irreversible.
    pass
