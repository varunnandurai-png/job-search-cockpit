"""Persist opaque one-use local manual mapping attempts.

Revision ID: 0018_local_manual_mapping_attempts
Revises: 0017_drive_reserved_file_ids
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018_local_manual_mapping_attempts"
down_revision: str | None = "0017_drive_reserved_file_ids"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "phase2_local_manual_mapping_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("attempt_id", sa.String(120), nullable=False, unique=True),
        sa.Column("nonce_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("phase1_authorization_id", sa.String(120), nullable=False, unique=True),
        sa.Column(
            "job_revision_id",
            sa.String(36),
            sa.ForeignKey("phase2_job_revisions.id"),
            nullable=False,
        ),
        sa.Column("selected_location_path_fingerprint", sa.String(64), nullable=False),
        sa.Column("coverage_ledger_fingerprint", sa.String(64), nullable=False),
        sa.Column("manifest_fingerprint", sa.String(64), nullable=False),
        sa.Column("logical_payload_digest", sa.String(64), nullable=False),
        sa.Column("rubric_version", sa.String(64), nullable=False),
        sa.Column("retrieval_configuration_version", sa.String(120), nullable=False),
        sa.Column("interpreter_configuration_version", sa.String(120), nullable=False),
        sa.Column("response_schema_version", sa.String(120), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(32), nullable=False, server_default="authorized"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("phase1_profile_fingerprint", sa.String(64), nullable=False),
        sa.Column("phase1_profile_generation", sa.Integer(), nullable=False),
        sa.Column("phase1_readiness_fingerprint", sa.String(64), nullable=False),
        sa.Column("phase1_readiness_generation", sa.Integer(), nullable=False),
        sa.Column("phase1_authority_fingerprint", sa.String(64), nullable=False),
        sa.Column("phase1_authority_generation", sa.Integer(), nullable=False),
        sa.Column("phase1_restore_generation", sa.Integer(), nullable=False),
        sa.Column("phase2_activation_generation", sa.Integer(), nullable=False),
        sa.Column("phase2_restore_generation", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "state IN ('authorized', 'consuming', 'validated_response', "
            "'expired', 'denied', 'failed', 'indeterminate', 'cancelled')"
        ),
    )
    op.create_table(
        "phase2_local_manual_mapping_attempt_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "attempt_id",
            sa.String(36),
            sa.ForeignKey("phase2_local_manual_mapping_attempts.id"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("reason_code", sa.String(120), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("attempt_id", "sequence"),
    )
    for table in (
        "phase2_local_manual_mapping_attempts",
        "phase2_local_manual_mapping_attempt_events",
    ):
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
