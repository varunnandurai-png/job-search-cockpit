from datetime import UTC, datetime
from typing import Any, ClassVar

from sqlalchemy import (
    JSON,
    Boolean,
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


class AssessmentAuthorityFence:
    """Generation snapshots required before an assessment can be treated as current."""

    phase1_profile_fingerprint: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="unbound"
    )
    phase1_profile_generation: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="-1"
    )
    phase1_readiness_fingerprint: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="unbound"
    )
    phase1_readiness_generation: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="-1"
    )
    phase1_authority_fingerprint: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="unbound"
    )
    phase1_authority_generation: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="-1"
    )
    phase1_restore_generation: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="-1"
    )
    phase2_activation_generation: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="-1"
    )
    phase2_restore_generation: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="-1"
    )


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


class Phase2FinalArtifact(Phase2Base):
    __tablename__ = "phase2_final_artifacts"
    __table_args__ = (UniqueConstraint("resume_preparation_attempt_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    resume_preparation_attempt_id: Mapped[str] = mapped_column(
        ForeignKey("phase2_resume_preparation_attempts.id")
    )
    job_id: Mapped[str] = mapped_column(String(120))
    job_revision_id: Mapped[str] = mapped_column(String(120))
    projection_fingerprint: Mapped[str] = mapped_column(String(64))
    content_fingerprint: Mapped[str] = mapped_column(String(64))
    docx_relative_path: Mapped[str] = mapped_column(String(260))
    docx_sha256: Mapped[str] = mapped_column(String(64))
    pdf_relative_path: Mapped[str] = mapped_column(String(260))
    pdf_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Phase2ResumeRequirementLedger(Phase2Base):
    __tablename__ = "phase2_resume_requirement_ledgers"
    __table_args__ = (
        CheckConstraint(
            "source_kind = 'phase2_assessment'",
            name="ck_phase2_resume_requirement_ledger_source",
        ),
        UniqueConstraint(
            "job_revision_id",
            "requirement_ledger_fingerprint",
            name="uq_phase2_resume_requirement_ledger_fingerprint",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("phase2_job_records.id"))
    job_revision_id: Mapped[str] = mapped_column(ForeignKey("phase2_job_revisions.id"))
    requirement_ids_json: Mapped[list[object]] = mapped_column(JSON)
    requirement_ledger_fingerprint: Mapped[str] = mapped_column(String(64))
    source_kind: Mapped[str] = mapped_column(String(32), default="phase2_assessment")
    phase2_activation_generation: Mapped[int] = mapped_column(Integer)
    phase2_restore_generation: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Phase2ResumeDocumentAttempt(Phase2Base):
    __tablename__ = "phase2_resume_document_attempts"
    __table_args__ = (
        UniqueConstraint("authorization_id"),
        UniqueConstraint("authorization_nonce"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(120))
    job_revision_id: Mapped[str] = mapped_column(String(120))
    requirement_ledger_id: Mapped[str] = mapped_column(
        ForeignKey("phase2_resume_requirement_ledgers.id")
    )
    requirement_ledger_fingerprint: Mapped[str] = mapped_column(String(64))
    requirement_ids_json: Mapped[list[object]] = mapped_column(JSON)
    authorization_id: Mapped[str] = mapped_column(String(120))
    authorization_nonce: Mapped[str] = mapped_column(String(120))
    authorization_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    projection_fingerprint: Mapped[str] = mapped_column(String(64))
    canonical_model_fingerprint: Mapped[str] = mapped_column(String(64))
    phase1_profile_fingerprint: Mapped[str] = mapped_column(String(64))
    phase1_profile_generation: Mapped[int] = mapped_column(Integer)
    phase1_readiness_fingerprint: Mapped[str] = mapped_column(String(64))
    phase1_readiness_generation: Mapped[int] = mapped_column(Integer)
    phase1_authority_fingerprint: Mapped[str] = mapped_column(String(64))
    phase1_authority_generation: Mapped[int] = mapped_column(Integer)
    phase1_restore_generation: Mapped[int] = mapped_column(Integer)
    phase2_activation_generation: Mapped[int] = mapped_column(Integer)
    phase2_restore_generation: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Phase2ResumeDocumentAttemptEvent(Phase2Base):
    __tablename__ = "phase2_resume_document_attempt_events"
    __table_args__ = (
        CheckConstraint(
            "kind = 'finalisation_failed'",
            name="ck_phase2_resume_document_attempt_event_kind",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    attempt_id: Mapped[str] = mapped_column(ForeignKey("phase2_resume_document_attempts.id"))
    kind: Mapped[str] = mapped_column(String(32), default="finalisation_failed")
    reason_code: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Phase2FinalResumeArtifact(Phase2Base):
    __tablename__ = "phase2_final_resume_artifacts"
    __table_args__ = (UniqueConstraint("attempt_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    attempt_id: Mapped[str] = mapped_column(ForeignKey("phase2_resume_document_attempts.id"))
    job_id: Mapped[str] = mapped_column(String(120))
    job_revision_id: Mapped[str] = mapped_column(String(120))
    projection_fingerprint: Mapped[str] = mapped_column(String(64))
    content_fingerprint: Mapped[str] = mapped_column(String(64))
    docx_relative_path: Mapped[str] = mapped_column(String(260))
    docx_sha256: Mapped[str] = mapped_column(String(64))
    docx_byte_length: Mapped[int] = mapped_column(Integer)
    pdf_relative_path: Mapped[str] = mapped_column(String(260))
    pdf_sha256: Mapped[str] = mapped_column(String(64))
    pdf_byte_length: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Phase2DiscoveryRun(Phase2Base):
    __tablename__ = "phase2_discovery_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    phase1_profile_fingerprint: Mapped[str] = mapped_column(String(64))
    phase1_profile_generation: Mapped[int] = mapped_column(Integer)
    phase1_readiness_fingerprint: Mapped[str] = mapped_column(String(64))
    phase1_readiness_generation: Mapped[int] = mapped_column(Integer)
    phase1_authority_fingerprint: Mapped[str] = mapped_column(String(64))
    phase1_authority_generation: Mapped[int] = mapped_column(Integer)
    phase1_restore_generation: Mapped[int] = mapped_column(Integer)
    phase2_activation_generation: Mapped[int] = mapped_column(Integer)
    phase2_restore_generation: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Phase2ProviderInstanceApproval(Phase2Base):
    __tablename__ = "phase2_provider_instance_approvals"
    __table_args__ = (UniqueConstraint("approval_fingerprint"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    instance_id: Mapped[str] = mapped_column(String(120))
    provider_kind: Mapped[str] = mapped_column(String(64))
    employer_identity: Mapped[str] = mapped_column(String(240))
    hosts_json: Mapped[list[object]] = mapped_column(JSON)
    endpoint_url: Mapped[str] = mapped_column(String(2048))
    redirect_hosts_json: Mapped[list[object]] = mapped_column(JSON)
    path_prefixes_json: Mapped[list[object]] = mapped_column(JSON)
    parser_version: Mapped[str] = mapped_column(String(120))
    content_types_json: Mapped[list[object]] = mapped_column(JSON)
    source_identifier: Mapped[str | None] = mapped_column(String(240))
    max_response_bytes: Mapped[int] = mapped_column(Integer)
    min_request_interval_seconds: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean)
    actor: Mapped[str] = mapped_column(String(120))
    reason: Mapped[str] = mapped_column(Text)
    phase2_activation_generation: Mapped[int] = mapped_column(Integer)
    phase2_restore_generation: Mapped[int] = mapped_column(Integer)
    approval_fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Phase2ProviderInstanceHealthEvent(Phase2Base):
    __tablename__ = "phase2_provider_instance_health_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider_instance_approval_id: Mapped[str] = mapped_column(
        ForeignKey("phase2_provider_instance_approvals.id")
    )
    outcome_code: Mapped[str] = mapped_column(String(64))
    request_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    request_finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    response_fingerprint: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Phase2SourceListingObservation(Phase2Base):
    __tablename__ = "phase2_source_listing_observations"
    __table_args__ = (
        UniqueConstraint(
            "provider_id",
            "source_listing_id",
            "content_fingerprint",
            name="uq_phase2_source_listing_observation_fingerprint",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    discovery_run_id: Mapped[str] = mapped_column(
        ForeignKey("phase2_discovery_runs.id")
    )
    provider_id: Mapped[str] = mapped_column(String(120))
    provider_run_id: Mapped[str | None] = mapped_column(String(120))
    source_listing_id: Mapped[str] = mapped_column(String(240))
    canonical_url: Mapped[str] = mapped_column(String(2048))
    title: Mapped[str] = mapped_column(Text)
    employer_name: Mapped[str] = mapped_column(Text)
    locations_json: Mapped[list[object]] = mapped_column(JSON)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    public_description: Mapped[str] = mapped_column(Text)
    compensation_text: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raw_content_fingerprint: Mapped[str] = mapped_column(String(64))
    content_fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Phase2JobRecord(Phase2Base):
    __tablename__ = "phase2_job_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    posting_identity_fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Phase2JobRevision(Phase2Base):
    __tablename__ = "phase2_job_revisions"
    __table_args__ = (
        UniqueConstraint(
            "job_record_id",
            "content_fingerprint",
            name="uq_phase2_job_revision_fingerprint",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_record_id: Mapped[str] = mapped_column(ForeignKey("phase2_job_records.id"))
    source_observation_id: Mapped[str] = mapped_column(
        ForeignKey("phase2_source_listing_observations.id")
    )
    canonical_url: Mapped[str] = mapped_column(String(2048))
    title: Mapped[str] = mapped_column(Text)
    employer_name: Mapped[str] = mapped_column(Text)
    locations_json: Mapped[list[object]] = mapped_column(JSON)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    public_description: Mapped[str] = mapped_column(Text)
    compensation_text: Mapped[str | None] = mapped_column(Text)
    content_fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Phase2JobVerification(Phase2Base):
    __tablename__ = "phase2_job_verifications"
    __table_args__ = (
        UniqueConstraint("authorization_id"),
        UniqueConstraint("authorization_nonce"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    authorization_id: Mapped[str] = mapped_column(String(120))
    authorization_nonce: Mapped[str] = mapped_column(String(120))
    job_revision_id: Mapped[str] = mapped_column(ForeignKey("phase2_job_revisions.id"))
    selected_location_path_fingerprint: Mapped[str] = mapped_column(String(64))
    source_observation_fingerprint: Mapped[str] = mapped_column(String(64))
    phase1_profile_fingerprint: Mapped[str] = mapped_column(String(64))
    phase1_profile_generation: Mapped[int] = mapped_column(Integer)
    phase1_readiness_fingerprint: Mapped[str] = mapped_column(String(64))
    phase1_readiness_generation: Mapped[int] = mapped_column(Integer)
    phase1_authority_fingerprint: Mapped[str] = mapped_column(String(64))
    phase1_authority_generation: Mapped[int] = mapped_column(Integer)
    phase1_restore_generation: Mapped[int] = mapped_column(Integer)
    phase2_activation_generation: Mapped[int] = mapped_column(Integer)
    phase2_restore_generation: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Phase2JobGateAssessment(AssessmentAuthorityFence, Phase2Base):
    __tablename__ = "phase2_job_gate_assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_revision_id: Mapped[str] = mapped_column(ForeignKey("phase2_job_revisions.id"))
    profile_fingerprint: Mapped[str] = mapped_column(String(64))
    result: Mapped[str] = mapped_column(String(16))
    reason_codes_json: Mapped[list[object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Phase2LocationEligibilityPath(AssessmentAuthorityFence, Phase2Base):
    __tablename__ = "phase2_location_eligibility_paths"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_gate_assessment_id: Mapped[str] = mapped_column(
        ForeignKey("phase2_job_gate_assessments.id")
    )
    location_fingerprint: Mapped[str] = mapped_column(String(64))
    result: Mapped[str] = mapped_column(String(16))
    reason_codes_json: Mapped[list[object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Phase2MatchAssessment(AssessmentAuthorityFence, Phase2Base):
    __tablename__ = "phase2_match_assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_revision_id: Mapped[str] = mapped_column(ForeignKey("phase2_job_revisions.id"))
    job_gate_assessment_id: Mapped[str] = mapped_column(
        ForeignKey("phase2_job_gate_assessments.id")
    )
    rubric_version: Mapped[str] = mapped_column(String(64))
    coverage_ledger_fingerprint: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="unbound"
    )
    total_score: Mapped[int] = mapped_column(Integer)
    qualified_band: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="unbound"
    )
    critical_floors_pass: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="0"
    )
    meaningful_role_and_responsibility: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="0"
    )
    worthwhile_structure: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    unsupported_required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    confidence: Mapped[str] = mapped_column(String(16))
    assessment_state: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="unbound"
    )
    fact_set_fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Phase2MatchComponent(AssessmentAuthorityFence, Phase2Base):
    __tablename__ = "phase2_match_components"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    match_assessment_id: Mapped[str] = mapped_column(ForeignKey("phase2_match_assessments.id"))
    component: Mapped[str] = mapped_column(String(32))
    score: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Phase2RequirementMapping(AssessmentAuthorityFence, Phase2Base):
    __tablename__ = "phase2_requirement_mappings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    match_assessment_id: Mapped[str] = mapped_column(ForeignKey("phase2_match_assessments.id"))
    requirement_id: Mapped[str] = mapped_column(String(120))
    requirement_kind: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="unbound"
    )
    component: Mapped[str] = mapped_column(String(32), nullable=False, server_default="unbound")
    source_span_id: Mapped[str] = mapped_column(
        String(120), nullable=False, server_default="unbound"
    )
    source_start_offset: Mapped[int] = mapped_column(Integer, nullable=False, server_default="-1")
    source_end_offset: Mapped[int] = mapped_column(Integer, nullable=False, server_default="-1")
    claim_id: Mapped[str | None] = mapped_column(String(120))
    fact_revision_id: Mapped[str | None] = mapped_column(String(120))
    support_assertion_id: Mapped[str | None] = mapped_column(String(120))
    relation: Mapped[str] = mapped_column(String(16))
    reason_code: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Phase2ShortlistDecision(AssessmentAuthorityFence, Phase2Base):
    __tablename__ = "phase2_shortlist_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    match_assessment_id: Mapped[str] = mapped_column(ForeignKey("phase2_match_assessments.id"))
    decision: Mapped[str] = mapped_column(String(32))
    reason_codes_json: Mapped[list[object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
