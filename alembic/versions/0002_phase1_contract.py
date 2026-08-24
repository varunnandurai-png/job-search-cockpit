"""Create durable Phase I activation-contract records.

Revision ID: 0002_phase1_contract
Revises: 0001_phase_1_vault
Create Date: 2026-08-24
"""

from collections.abc import Sequence

from alembic import op
from job_search_cockpit.storage.models import Base

revision: str = "0002_phase1_contract"
down_revision: str | None = "0001_phase_1_vault"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())
    op.execute(
        "INSERT OR IGNORE INTO phase1_authority_state "
        "(id, authority_high_water_mark, readiness_generation, active_profile_generation, "
        "restore_generation) VALUES (1, 0, 0, 0, 0)"
    )
    for operation in ("update", "delete"):
        op.execute(f"DROP TRIGGER IF EXISTS prevent_phase1_acceptance_receipts_{operation}")
        op.execute(
            f"""
            CREATE TRIGGER prevent_phase1_acceptance_receipts_{operation}
            BEFORE {operation.upper()} ON phase1_acceptance_receipts
            BEGIN
                SELECT RAISE(ABORT, 'phase1_acceptance_receipts is append-only');
            END
            """
        )


def downgrade() -> None:
    for operation in ("update", "delete"):
        op.execute(f"DROP TRIGGER IF EXISTS prevent_phase1_acceptance_receipts_{operation}")
    Base.metadata.drop_all(bind=op.get_bind())
