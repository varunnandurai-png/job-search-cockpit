"""Persist official provider instance content-type policy.

Revision ID: 0010_provider_instance_content_types
Revises: 0009_official_provider_instances
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_provider_instance_content_types"
down_revision: str | None = "0009_official_provider_instances"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns(
            "phase2_provider_instance_approvals"
        )
    }
    if "content_types_json" not in columns:
        op.add_column(
            "phase2_provider_instance_approvals",
            sa.Column(
                "content_types_json",
                sa.JSON(),
                nullable=False,
                server_default='["application/json"]',
            ),
        )


def downgrade() -> None:
    pass
