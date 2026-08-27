"""Persist immutable official provider source identifiers.

Revision ID: 0011_provider_instance_source_identifier
Revises: 0010_provider_instance_content_types
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_provider_instance_source_identifier"
down_revision: str | None = "0010_provider_instance_content_types"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns(
            "phase2_provider_instance_approvals"
        )
    }
    if "source_identifier" not in columns:
        op.add_column(
            "phase2_provider_instance_approvals",
            sa.Column("source_identifier", sa.String(length=240), nullable=True),
        )


def downgrade() -> None:
    pass
