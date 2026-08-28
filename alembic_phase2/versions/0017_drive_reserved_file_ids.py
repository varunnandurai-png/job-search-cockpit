"""Persist both reserved Drive file identifiers for safe manual retry.

Revision ID: 0017_drive_reserved_file_ids
Revises: 0016_private_drive_backup
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017_drive_reserved_file_ids"
down_revision: str | None = "0016_private_drive_backup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    table = "phase2_drive_backup_events"
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}
    for name in ("docx_file_id", "pdf_file_id"):
        if name not in existing:
            op.add_column(table, sa.Column(name, sa.String(length=255), nullable=True))


def downgrade() -> None:
    # Backup audit history is intentionally irreversible.
    pass
