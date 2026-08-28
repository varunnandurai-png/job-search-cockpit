"""Add append-only private Google Drive backup metadata.

Revision ID: 0016_private_drive_backup
Revises: 0015_match_assessment_band_inputs
Create Date: 2026-08-28
"""

from collections.abc import Sequence

from alembic import op
from job_search_cockpit.phase2.models import Phase2DriveBackupEvent, Phase2DriveBackupOperation

revision: str = "0016_private_drive_backup"
down_revision: str | None = "0015_match_assessment_band_inputs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    Phase2DriveBackupOperation.__table__,
    Phase2DriveBackupEvent.__table__,
)


def upgrade() -> None:
    for table in _TABLES:
        table.create(bind=op.get_bind(), checkfirst=True)
        for operation in ("update", "delete"):
            op.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS prevent_{table.name}_{operation}
                BEFORE {operation.upper()} ON {table.name}
                BEGIN
                    SELECT RAISE(ABORT, '{table.name} is append-only');
                END
                """
            )


def downgrade() -> None:
    # Backup audit history is intentionally irreversible.
    pass
