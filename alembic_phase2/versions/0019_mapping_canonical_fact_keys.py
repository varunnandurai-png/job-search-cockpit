"""Bind published Phase II mappings to canonical Phase I fact keys.

Revision ID: 0019_mapping_canonical_fact_keys
Revises: 0018_local_manual_mapping_attempts
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019_mapping_canonical_fact_keys"
down_revision: str | None = "0018_local_manual_mapping_attempts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    table = "phase2_requirement_mappings"
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}
    if "canonical_fact_key" not in columns:
        op.add_column(table, sa.Column("canonical_fact_key", sa.String(length=255), nullable=True))
    for operation in ("update", "delete"):
        op.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS prevent_{table}_{operation}
            BEFORE {operation.upper()} ON {table}
            BEGIN
                SELECT RAISE(ABORT, '{table} is append-only');
            END
            """
        )


def downgrade() -> None:
    pass
