"""Persist opaque citation and fact references for requirement mappings.

Revision ID: 0013_requirement_mapping_references
Revises: 0012_assessment_authority_fences
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013_requirement_mapping_references"
down_revision: str | None = "0012_assessment_authority_fences"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    table = "phase2_requirement_mappings"
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}
    required = (
        sa.Column(
            "requirement_kind", sa.String(length=32), nullable=False, server_default="unbound"
        ),
        sa.Column("component", sa.String(length=32), nullable=False, server_default="unbound"),
        sa.Column(
            "source_span_id", sa.String(length=120), nullable=False, server_default="unbound"
        ),
        sa.Column("source_start_offset", sa.Integer(), nullable=False, server_default="-1"),
        sa.Column("source_end_offset", sa.Integer(), nullable=False, server_default="-1"),
        sa.Column("fact_revision_id", sa.String(length=120), nullable=True),
        sa.Column("support_assertion_id", sa.String(length=120), nullable=True),
    )
    for column in required:
        if column.name not in existing:
            op.add_column(table, column)


def downgrade() -> None:
    pass
