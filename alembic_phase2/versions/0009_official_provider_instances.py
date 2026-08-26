"""Add append-only official provider instance metadata.

Revision ID: 0009_official_provider_instances
Revises: 0008_match_scoring_shortlist
Create Date: 2026-08-26
"""

from collections.abc import Sequence

from alembic import op
from job_search_cockpit.phase2.models import (
    Phase2ProviderInstanceApproval,
    Phase2ProviderInstanceHealthEvent,
)

revision: str = "0009_official_provider_instances"
down_revision: str | None = "0008_match_scoring_shortlist"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    Phase2ProviderInstanceApproval.__table__,
    Phase2ProviderInstanceHealthEvent.__table__,
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
