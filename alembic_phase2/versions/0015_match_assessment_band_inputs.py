"""Persist fail-closed qualified-band inputs for immutable assessments.

Revision ID: 0015_match_assessment_band_inputs
Revises: 0014_match_assessment_publication_metadata
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015_match_assessment_band_inputs"
down_revision: str | None = "0014_match_assessment_publication_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    table = "phase2_match_assessments"
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}
    required = (
        sa.Column("critical_floors_pass", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column(
            "meaningful_role_and_responsibility", sa.Boolean(), nullable=False, server_default="0"
        ),
        sa.Column("worthwhile_structure", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("unsupported_required", sa.Boolean(), nullable=False, server_default="0"),
    )
    for column in required:
        if column.name not in existing:
            op.add_column(table, column)


def downgrade() -> None:
    pass
