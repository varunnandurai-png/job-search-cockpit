"""Add the Phase I matching-disclosure boundary.

Revision ID: 0003_phase1_matching_disclosure
Revises: 0002_phase1_contract
Create Date: 2026-08-31
"""

from collections.abc import Sequence

from alembic import op
from job_search_cockpit.storage.models import Base

revision: str = "0003_phase1_matching_disclosure"
down_revision: str | None = "0002_phase1_contract"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "phase1_matching_disclosure_epochs",
    "phase1_matching_retrieval_preflights",
    "phase1_fact_disclosure_authorizations",
    "phase1_fact_disclosure_authorization_facts",
    "phase1_fact_disclosure_authorization_taxonomy",
    "phase1_fact_disclosure_lifecycle_events",
    "phase1_fact_disclosure_release_events",
)


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in _TABLES:
        Base.metadata.tables[table_name].create(bind=bind, checkfirst=True)
    op.execute(
        "INSERT OR IGNORE INTO phase1_matching_disclosure_epochs "
        "(id, epoch_number, policy_generation, reason, confirmation, created_at) "
        "VALUES ('phase1-disclosure-epoch-1', 1, 1, 'Initial matching disclosure epoch', "
        "'SYSTEM INITIALIZATION', CURRENT_TIMESTAMP)"
    )
    for table_name in _TABLES:
        for operation in ("update", "delete"):
            trigger = f"prevent_{table_name}_{operation}"
            op.execute(f"DROP TRIGGER IF EXISTS {trigger}")
            op.execute(
                f"""
                CREATE TRIGGER {trigger}
                BEFORE {operation.upper()} ON {table_name}
                BEGIN
                    SELECT RAISE(ABORT, '{table_name} is append-only');
                END
                """
            )


def downgrade() -> None:
    # Disclosure history is intentionally non-destructive. A rollback may stop
    # using these additive tables, but it must not erase authorization evidence.
    pass
