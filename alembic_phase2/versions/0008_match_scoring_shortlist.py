"""Add append-only Phase II scoring metadata.

Revision ID: 0008_match_scoring_shortlist
Revises: 0007_resume_finalisation
Create Date: 2026-08-26
"""

from collections.abc import Sequence

from alembic import op
from job_search_cockpit.phase2.models import (
    Phase2JobGateAssessment,
    Phase2LocationEligibilityPath,
    Phase2MatchAssessment,
    Phase2MatchComponent,
    Phase2RequirementMapping,
    Phase2ShortlistDecision,
)

revision: str = "0008_match_scoring_shortlist"
down_revision: str | None = "0007_resume_finalisation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    Phase2JobGateAssessment.__table__,
    Phase2LocationEligibilityPath.__table__,
    Phase2MatchAssessment.__table__,
    Phase2MatchComponent.__table__,
    Phase2RequirementMapping.__table__,
    Phase2ShortlistDecision.__table__,
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
    pass
