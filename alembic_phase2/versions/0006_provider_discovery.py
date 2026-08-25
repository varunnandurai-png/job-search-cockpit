"""Add append-only provider discovery catalog records.

Revision ID: 0006_provider_discovery
Revises: 0005_final_artifact_metadata
Create Date: 2026-08-25
"""

from collections.abc import Sequence

from alembic import op
from job_search_cockpit.phase2.models import (
    Phase2DiscoveryRun,
    Phase2JobRecord,
    Phase2JobRevision,
    Phase2JobVerification,
    Phase2SourceListingObservation,
)

revision: str = "0006_provider_discovery"
down_revision: str | None = "0005_final_artifact_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    Phase2DiscoveryRun.__table__,
    Phase2SourceListingObservation.__table__,
    Phase2JobRecord.__table__,
    Phase2JobRevision.__table__,
    Phase2JobVerification.__table__,
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
    # Discovery provenance is intentionally irreversible.
    pass
