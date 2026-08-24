"""Create Phase II activation-only storage.

Revision ID: 0001_phase2_activation
Revises:
Create Date: 2026-08-24
"""

from collections.abc import Sequence

from alembic import op
from job_search_cockpit.phase2.models import Phase2Base

revision: str = "0001_phase2_activation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    Phase2Base.metadata.create_all(bind=op.get_bind())
    op.execute(
        "INSERT OR IGNORE INTO phase2_authority_state "
        "(id, restore_generation, revocation_generation, activation_generation, current_grant_id) "
        "VALUES (1, 0, 0, 0, NULL)"
    )
    for operation in ("update", "delete"):
        op.execute(
            f"""
            CREATE TRIGGER prevent_phase2_activation_grants_{operation}
            BEFORE {operation.upper()} ON phase2_activation_grants
            BEGIN
                SELECT RAISE(ABORT, 'phase2_activation_grants is append-only');
            END
            """
        )


def downgrade() -> None:
    for operation in ("update", "delete"):
        op.execute(f"DROP TRIGGER IF EXISTS prevent_phase2_activation_grants_{operation}")
    Phase2Base.metadata.drop_all(bind=op.get_bind())
