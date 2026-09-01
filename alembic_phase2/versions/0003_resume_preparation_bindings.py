"""Bind résumé-preparation attempts to immutable authorization state.

Revision ID: 0003_resume_preparation_bindings
Revises: 0002_resume_preparation_attempts
Create Date: 2026-08-24
"""

from collections.abc import Sequence

from sqlalchemy import Column, Integer, String, inspect

from alembic import op

revision: str = "0003_resume_preparation_bindings"
down_revision: str | None = "0002_resume_preparation_attempts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "phase2_resume_preparation_attempts"
_COLUMNS = (
    ("selected_location_path_fingerprint", String(64)),
    ("authorization_nonce", String(120)),
    ("phase1_profile_fingerprint", String(64)),
    ("phase1_profile_generation", Integer()),
    ("phase1_readiness_fingerprint", String(64)),
    ("phase1_readiness_generation", Integer()),
    ("phase1_authority_fingerprint", String(64)),
    ("phase1_authority_generation", Integer()),
    ("phase1_restore_generation", Integer()),
    ("phase2_activation_generation", Integer()),
    ("phase2_restore_generation", Integer()),
)


def _replace_append_only_triggers() -> None:
    for operation in ("update", "delete"):
        op.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS prevent_{_TABLE}_{operation}
            BEFORE {operation.upper()} ON {_TABLE}
            BEGIN
                SELECT RAISE(ABORT, '{_TABLE} is append-only');
            END
            """
        )


def upgrade() -> None:
    bind = op.get_bind()
    existing = {column["name"] for column in inspect(bind).get_columns(_TABLE)}
    missing = [(name, column_type) for name, column_type in _COLUMNS if name not in existing]
    if not missing:
        return
    for operation in ("update", "delete"):
        op.execute(f"DROP TRIGGER IF EXISTS prevent_{_TABLE}_{operation}")
    with op.batch_alter_table(_TABLE) as batch:
        for name, column_type in missing:
            batch.add_column(Column(name, column_type, nullable=True))
        batch.create_unique_constraint(
            "uq_phase2_resume_preparation_nonce", ["authorization_nonce"]
        )
    _replace_append_only_triggers()


def downgrade() -> None:
    # Historical attempts must remain append-only; this safety migration is irreversible.
    pass
