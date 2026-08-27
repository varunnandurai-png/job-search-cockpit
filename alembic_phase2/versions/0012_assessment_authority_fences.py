"""Bind Phase II assessment metadata to Phase I and Phase II generations.

Revision ID: 0012_assessment_authority_fences
Revises: 0011_provider_instance_source_identifier
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_assessment_authority_fences"
down_revision: str | None = "0011_provider_instance_source_identifier"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "phase2_job_gate_assessments",
    "phase2_location_eligibility_paths",
    "phase2_match_assessments",
    "phase2_match_components",
    "phase2_requirement_mappings",
    "phase2_shortlist_decisions",
)
_TEXT_COLUMNS = (
    "phase1_profile_fingerprint",
    "phase1_readiness_fingerprint",
    "phase1_authority_fingerprint",
)
_INTEGER_COLUMNS = (
    "phase1_profile_generation",
    "phase1_readiness_generation",
    "phase1_authority_generation",
    "phase1_restore_generation",
    "phase2_activation_generation",
    "phase2_restore_generation",
)


def upgrade() -> None:
    bind = op.get_bind()
    for table in _TABLES:
        existing = {column["name"] for column in sa.inspect(bind).get_columns(table)}
        for name in _TEXT_COLUMNS:
            if name not in existing:
                op.add_column(
                    table,
                    sa.Column(
                        name,
                        sa.String(length=64),
                        nullable=False,
                        server_default="unbound",
                    ),
                )
        for name in _INTEGER_COLUMNS:
            if name not in existing:
                op.add_column(
                    table,
                    sa.Column(name, sa.Integer(), nullable=False, server_default="-1"),
                )


def downgrade() -> None:
    pass
