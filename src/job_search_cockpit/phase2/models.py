from datetime import UTC, datetime
from typing import Any, ClassVar

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
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


class Phase2ReusableAnswer(Phase2Base):
    __tablename__ = "phase2_reusable_answers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    question_label_fingerprint: Mapped[str] = mapped_column(String(64))
    phase1_revision_id: Mapped[str] = mapped_column(String(120))
    projection_fingerprint: Mapped[str] = mapped_column(String(64))
    supersedes_answer_id: Mapped[str | None] = mapped_column(
        ForeignKey("phase2_reusable_answers.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Phase2ApplicationDraft(Phase2Base):
    __tablename__ = "phase2_application_drafts"
    __table_args__ = (
        CheckConstraint(
            "state = 'manual_review_required_no_submission'",
            name="ck_phase2_application_draft_no_submission",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    resume_preparation_attempt_id: Mapped[str] = mapped_column(
        ForeignKey("phase2_resume_preparation_attempts.id")
    )
    job_id: Mapped[str] = mapped_column(String(120))
    job_revision_id: Mapped[str] = mapped_column(String(120))
    final_resume_version_id: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(
        String(64), default="manual_review_required_no_submission"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Phase2ApplicationDraftAnswer(Phase2Base):
    __tablename__ = "phase2_application_draft_answers"
    __table_args__ = (UniqueConstraint("application_draft_id", "reusable_answer_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    application_draft_id: Mapped[str] = mapped_column(
        ForeignKey("phase2_application_drafts.id")
    )
    reusable_answer_id: Mapped[str] = mapped_column(ForeignKey("phase2_reusable_answers.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Phase2ApplicationDraftReviewFlag(Phase2Base):
    __tablename__ = "phase2_application_draft_review_flags"
    __table_args__ = (
        CheckConstraint(
            "reason = 'approved_answer_superseded'",
            name="ck_phase2_application_draft_review_flag_reason",
        ),
        UniqueConstraint("application_draft_id", "superseded_answer_id", "replacement_answer_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    application_draft_id: Mapped[str] = mapped_column(
        ForeignKey("phase2_application_drafts.id")
    )
    superseded_answer_id: Mapped[str] = mapped_column(ForeignKey("phase2_reusable_answers.id"))
    replacement_answer_id: Mapped[str] = mapped_column(ForeignKey("phase2_reusable_answers.id"))
    reason: Mapped[str] = mapped_column(String(64), default="approved_answer_superseded")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
