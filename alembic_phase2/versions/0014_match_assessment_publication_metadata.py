"""Persist qualified-band and stability metadata for match publication.

Revision ID: 0014_match_assessment_publication_metadata
Revises: 0013_requirement_mapping_references
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_match_assessment_publication_metadata"
down_revision: str | None = "0013_requirement_mapping_references"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    table = "phase2_match_assessments"
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}
    required = (
        sa.Column(
            "coverage_ledger_fingerprint",
            sa.String(length=64),
            nullable=False,
            server_default="unbound",
        ),
        sa.Column(
            "qualified_band", sa.String(length=32), nullable=False, server_default="unbound"
        ),
        sa.Column(
            "assessment_state", sa.String(length=32), nullable=False, server_default="unbound"
        ),
    )
    for column in required:
        if column.name not in existing:
            op.add_column(table, column)


def downgrade() -> None:
    pass
