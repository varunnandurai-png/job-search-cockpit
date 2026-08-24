from datetime import UTC, datetime
from typing import Any, ClassVar

from sqlalchemy import JSON, CheckConstraint, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Phase2Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {dict[str, object]: JSON}


class Phase2AuthorityState(Phase2Base):
    __tablename__ = "phase2_authority_state"
    __table_args__ = (CheckConstraint("id = 1", name="ck_phase2_authority_singleton"),)

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    restore_generation: Mapped[int] = mapped_column(Integer, default=0)
    revocation_generation: Mapped[int] = mapped_column(Integer, default=0)
    activation_generation: Mapped[int] = mapped_column(Integer, default=0)
    current_grant_id: Mapped[str | None] = mapped_column(String(36))


class Phase2ActivationGrant(Phase2Base):
    __tablename__ = "phase2_activation_grants"
    __table_args__ = (
        CheckConstraint(
            "state IN ('active', 'suspended', 'revoked')",
            name="ck_phase2_activation_grant_state",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    state: Mapped[str] = mapped_column(String(16))
    snapshot_json: Mapped[dict[str, object]] = mapped_column(JSON)
    snapshot_fingerprint: Mapped[str] = mapped_column(String(64))
    confirmation: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(120))
    expected_activation_generation: Mapped[int] = mapped_column(Integer)
    supersedes_grant_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Phase2ResumePreparationAttempt(Phase2Base):
    __tablename__ = "phase2_resume_preparation_attempts"
    __table_args__ = (
        UniqueConstraint("authorization_id"),
        UniqueConstraint("authorization_nonce", name="uq_phase2_resume_preparation_nonce"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(120))
    job_revision_id: Mapped[str] = mapped_column(String(120))
    selected_location_path_fingerprint: Mapped[str | None] = mapped_column(String(64))
    authorization_id: Mapped[str] = mapped_column(String(120))
    authorization_nonce: Mapped[str | None] = mapped_column(String(120))
    authorization_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    phase1_profile_fingerprint: Mapped[str | None] = mapped_column(String(64))
    phase1_profile_generation: Mapped[int | None] = mapped_column(Integer)
    phase1_readiness_fingerprint: Mapped[str | None] = mapped_column(String(64))
    phase1_readiness_generation: Mapped[int | None] = mapped_column(Integer)
    phase1_authority_fingerprint: Mapped[str | None] = mapped_column(String(64))
    phase1_authority_generation: Mapped[int | None] = mapped_column(Integer)
    phase1_restore_generation: Mapped[int | None] = mapped_column(Integer)
    phase2_activation_generation: Mapped[int | None] = mapped_column(Integer)
    phase2_restore_generation: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
