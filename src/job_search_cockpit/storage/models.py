from collections.abc import Sequence
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any, ClassVar

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from job_search_cockpit.facts.types import Sensitivity


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _enum_values(enum_type: type[StrEnum]) -> Sequence[str]:
    return [member.value for member in enum_type]


class ClaimStatus(StrEnum):
    UNRESOLVED = "unresolved"
    APPROVED = "approved"
    CORRECTED = "corrected"
    REJECTED = "rejected"


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {dict[str, object]: JSON}


class SourceDocument(Base):
    __tablename__ = "source_documents"
    __table_args__ = (UniqueConstraint("path", "content_hash"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_key: Mapped[str] = mapped_column(String(64), index=True)
    path: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    size: Mapped[int]
    modified_ns: Mapped[int]
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SourceOccurrence(Base):
    __tablename__ = "source_occurrences"
    __table_args__ = (
        UniqueConstraint(
            "source_key",
            "subject_key",
            "employer_key",
            "period_start",
            "period_end",
            "statement_kind",
            "semantic_anchor",
            name="uq_source_occurrence_semantic_identity",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_key: Mapped[str] = mapped_column(String(64), index=True)
    subject_key: Mapped[str] = mapped_column(String(160), default="")
    employer_key: Mapped[str] = mapped_column(String(160), default="")
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    statement_kind: Mapped[str] = mapped_column(String(80))
    semantic_anchor: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ImportRun(Base):
    __tablename__ = "import_runs"
    __table_args__ = (
        CheckConstraint("status IN ('committed', 'incomplete')", name="ck_import_run_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    manifest_version: Mapped[str] = mapped_column(String(32))
    candidate_digest: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    complete: Mapped[bool] = mapped_column(Boolean)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    committed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ImportRunSource(Base):
    __tablename__ = "import_run_sources"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ready', 'missing', 'unreadable', 'malformed')",
            name="ck_import_run_source_status",
        ),
        UniqueConstraint("import_run_id", "source_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    import_run_id: Mapped[str] = mapped_column(ForeignKey("import_runs.id"), index=True)
    source_key: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    failure_class: Mapped[str | None] = mapped_column(String(120))
    redacted_message: Mapped[str | None] = mapped_column(Text)


class ImportAttempt(Base):
    __tablename__ = "import_attempts"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('committed', 'aborted', 'failed', 'rejected')",
            name="ck_import_attempt_outcome",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    preview_id: Mapped[str] = mapped_column(String(64), index=True)
    candidate_digest: Mapped[str] = mapped_column(String(64))
    manifest_version: Mapped[str] = mapped_column(String(32))
    outcome: Mapped[str] = mapped_column(String(16))
    source_statuses_json: Mapped[dict[str, object]] = mapped_column(JSON)
    failure_class: Mapped[str | None] = mapped_column(String(120))
    redacted_message: Mapped[str | None] = mapped_column(Text)
    session_fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    canonical_key: Mapped[str] = mapped_column(String(255), unique=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    subject: Mapped[str] = mapped_column(String(255))
    status: Mapped[ClaimStatus] = mapped_column(
        Enum(
            ClaimStatus,
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="claim_status",
        ),
        default=ClaimStatus.UNRESOLVED,
    )
    sensitivity: Mapped[Sensitivity] = mapped_column(
        Enum(
            Sensitivity,
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="sensitivity",
        ),
        default=Sensitivity.UNREVIEWED,
    )
    active_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("claim_revisions.id", use_alter=True, name="fk_claim_active_revision")
    )
    stale: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    revisions: Mapped[list["ClaimRevision"]] = relationship(
        back_populates="claim", foreign_keys="ClaimRevision.claim_id"
    )


class ClaimRevision(Base):
    __tablename__ = "claim_revisions"
    __table_args__ = (
        UniqueConstraint(
            "claim_id",
            "semantic_value",
            "employer_key",
            "period_start",
            "period_end",
            name="uq_claim_revision_semantic_identity",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id"), index=True)
    value_json: Mapped[dict[str, object]] = mapped_column(JSON)
    display_value: Mapped[str] = mapped_column(Text)
    semantic_value: Mapped[str] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(32))
    employer_key: Mapped[str] = mapped_column(String(160), default="")
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    claim: Mapped[Claim] = relationship(back_populates="revisions", foreign_keys=[claim_id])


class ClaimEvidence(Base):
    __tablename__ = "claim_evidence"
    __table_args__ = (
        UniqueConstraint(
            "revision_id",
            "source_occurrence_id",
            "source_hash",
            "locator",
            name="uq_claim_evidence_revision_occurrence",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision_id: Mapped[str] = mapped_column(ForeignKey("claim_revisions.id"), index=True)
    source_document_id: Mapped[str] = mapped_column(ForeignKey("source_documents.id"))
    source_occurrence_id: Mapped[str] = mapped_column(ForeignKey("source_occurrences.id"))
    source_key: Mapped[str] = mapped_column(String(64))
    source_hash: Mapped[str] = mapped_column(String(64))
    locator: Mapped[str] = mapped_column(Text)
    excerpt: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ClaimSupportAssertion(Base):
    __tablename__ = "claim_support_assertions"
    __table_args__ = (
        CheckConstraint(
            "support_state IN ('supported', 'unsupported')", name="ck_claim_support_state"
        ),
        CheckConstraint(
            "support_type IN ('documentary', 'user_confirmed', 'loss')",
            name="ck_claim_support_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id"), index=True)
    revision_id: Mapped[str] = mapped_column(ForeignKey("claim_revisions.id"), index=True)
    support_state: Mapped[str] = mapped_column(String(16))
    support_type: Mapped[str] = mapped_column(String(24))
    source_evidence_id: Mapped[str | None] = mapped_column(ForeignKey("claim_evidence.id"))
    employer_key: Mapped[str] = mapped_column(String(160), default="")
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    actor: Mapped[str] = mapped_column(String(120))
    reason: Mapped[str] = mapped_column(Text, default="")
    supersedes_assertion_id: Mapped[str | None] = mapped_column(
        ForeignKey("claim_support_assertions.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ImportRunOccurrence(Base):
    __tablename__ = "import_run_occurrences"
    __table_args__ = (UniqueConstraint("import_run_id", "source_occurrence_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    import_run_id: Mapped[str] = mapped_column(ForeignKey("import_runs.id"), index=True)
    source_occurrence_id: Mapped[str] = mapped_column(
        ForeignKey("source_occurrences.id"), index=True
    )
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id"))
    revision_id: Mapped[str] = mapped_column(ForeignKey("claim_revisions.id"))


class ConflictGroup(Base):
    __tablename__ = "conflict_groups"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'resolved')", name="ck_conflict_group_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    semantic_family: Mapped[str] = mapped_column(String(255), index=True)
    employer_key: Mapped[str] = mapped_column(String(160), default="")
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="open")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ConflictMember(Base):
    __tablename__ = "conflict_members"
    __table_args__ = (UniqueConstraint("conflict_group_id", "revision_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conflict_group_id: Mapped[str] = mapped_column(ForeignKey("conflict_groups.id"), index=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id"), index=True)
    revision_id: Mapped[str] = mapped_column(ForeignKey("claim_revisions.id"), index=True)


class ConflictResolution(Base):
    __tablename__ = "conflict_resolutions"
    __table_args__ = (
        CheckConstraint(
            "resolution_type IN ('selected', 'corrected', 'reopened', 'closed')",
            name="ck_conflict_resolution_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conflict_group_id: Mapped[str] = mapped_column(ForeignKey("conflict_groups.id"), index=True)
    resolution_type: Mapped[str] = mapped_column(String(16))
    selected_revision_id: Mapped[str | None] = mapped_column(ForeignKey("claim_revisions.id"))
    corrected_revision_id: Mapped[str | None] = mapped_column(ForeignKey("claim_revisions.id"))
    expected_group_version: Mapped[int]
    reason: Mapped[str] = mapped_column(Text)
    employer_key: Mapped[str] = mapped_column(String(160), default="")
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    supersedes_resolution_id: Mapped[str | None] = mapped_column(
        ForeignKey("conflict_resolutions.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = (
        CheckConstraint(
            "action IN ('approve', 'correct', 'confirm_support', 'reject', 'revert', "
            "'set_sensitivity', 'resolve_conflict')",
            name="ck_decision_action",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id"), index=True)
    revision_id: Mapped[str | None] = mapped_column(ForeignKey("claim_revisions.id"))
    action: Mapped[str] = mapped_column(String(24))
    status: Mapped[str | None] = mapped_column(String(16))
    sensitivity: Mapped[str | None] = mapped_column(String(16))
    actor: Mapped[str] = mapped_column(String(120), default="Varun")
    reason: Mapped[str] = mapped_column(Text, default="")
    expected_claim_version: Mapped[int]
    supersedes_decision_id: Mapped[str | None] = mapped_column(ForeignKey("decisions.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class NamedUse(Base):
    __tablename__ = "named_uses"
    __table_args__ = (UniqueConstraint("kind", "external_reference", "description"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(64))
    external_reference: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    creator: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ConfidentialPermissionEvent(Base):
    __tablename__ = "confidential_permission_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('grant', 'revoke', 'expire', 'supersede')",
            name="ck_permission_event_type",
        ),
        UniqueConstraint("permission_id", "event_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    permission_id: Mapped[str] = mapped_column(String(36), index=True)
    event_type: Mapped[str] = mapped_column(String(16))
    event_version: Mapped[int]
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id"), index=True)
    revision_id: Mapped[str] = mapped_column(ForeignKey("claim_revisions.id"))
    named_use_id: Mapped[str] = mapped_column(ForeignKey("named_uses.id"))
    actor: Mapped[str] = mapped_column(String(120))
    confirmation: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    target_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("confidential_permission_events.id")
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    area: Mapped[str] = mapped_column(String(80), index=True)
    subject_id: Mapped[str] = mapped_column(String(64), index=True)
    summary: Mapped[str] = mapped_column(Text)
    before_json: Mapped[dict[str, object] | None] = mapped_column(JSON)
    after_json: Mapped[dict[str, object] | None] = mapped_column(JSON)
    sensitive: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    reason: Mapped[str] = mapped_column(Text, default="", server_default="")
    source_label: Mapped[str] = mapped_column(String(255), default="", server_default="")
    supersedes_event_id: Mapped[str | None] = mapped_column(ForeignKey("audit_events.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SearchProfileVersion(Base):
    __tablename__ = "search_profile_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version_number: Mapped[int] = mapped_column(Integer, unique=True)
    payload_json: Mapped[dict[str, object]] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    confirmation: Mapped[str] = mapped_column(Text, default="")
    diff_digest: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Phase1AuthorityState(Base):
    __tablename__ = "phase1_authority_state"
    __table_args__ = (CheckConstraint("id = 1", name="ck_phase1_authority_singleton"),)

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    authority_high_water_mark: Mapped[int] = mapped_column(Integer, default=0)
    readiness_generation: Mapped[int] = mapped_column(Integer, default=0)
    active_profile_generation: Mapped[int] = mapped_column(Integer, default=0)
    restore_generation: Mapped[int] = mapped_column(Integer, default=0)


class Phase1AcceptanceReceipt(Base):
    __tablename__ = "phase1_acceptance_receipts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    application_build: Mapped[str] = mapped_column(String(160))
    schema_revision: Mapped[str] = mapped_column(String(80))
    acceptance_suite_version: Mapped[str] = mapped_column(String(120))
    acceptance_run_id: Mapped[str] = mapped_column(String(160), unique=True)
    result: Mapped[str] = mapped_column(String(16))
    result_fingerprint: Mapped[str] = mapped_column(String(64))
    restore_high_water_mark: Mapped[int] = mapped_column(Integer)
    actor: Mapped[str] = mapped_column(String(120))
    confirmation: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Phase1MatchingDisclosureEpoch(Base):
    __tablename__ = "phase1_matching_disclosure_epochs"
    __table_args__ = (
        UniqueConstraint("epoch_number"),
        UniqueConstraint("policy_generation"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    epoch_number: Mapped[int] = mapped_column(Integer)
    policy_generation: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    confirmation: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Phase1MatchingRetrievalPreflight(Base):
    __tablename__ = "phase1_matching_retrieval_preflights"
    __table_args__ = (
        UniqueConstraint(
            "job_revision_id",
            "coverage_ledger_fingerprint",
            "disclosure_budget_epoch",
            "phase1_authority_generation",
            name="uq_phase1_matching_preflight_scope",
        ),
        UniqueConstraint("manifest_fingerprint"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_revision_id: Mapped[str] = mapped_column(String(255))
    coverage_ledger_fingerprint: Mapped[str] = mapped_column(String(64))
    disclosure_budget_epoch: Mapped[int] = mapped_column(Integer)
    phase1_authority_generation: Mapped[int] = mapped_column(Integer)
    query_fingerprint: Mapped[str] = mapped_column(String(64))
    manifest_fingerprint: Mapped[str] = mapped_column(String(64))
    manifest_json: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Phase1FactDisclosureAuthorization(Base):
    __tablename__ = "phase1_fact_disclosure_authorizations"
    __table_args__ = (
        UniqueConstraint("attempt_id"),
        UniqueConstraint("logical_payload_digest"),
        CheckConstraint(
            "initial_state IN ('authorized', 'expired', 'denied', 'failed', 'indeterminate')",
            name="ck_phase1_fact_disclosure_initial_state",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    attempt_id: Mapped[str] = mapped_column(String(160), index=True)
    packet_id: Mapped[str] = mapped_column(String(160))
    nonce_sha256: Mapped[str] = mapped_column(String(64))
    phase2_authorization_id: Mapped[str] = mapped_column(String(160))
    preflight_id: Mapped[str] = mapped_column(
        ForeignKey("phase1_matching_retrieval_preflights.id")
    )
    manifest_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    logical_payload_digest: Mapped[str] = mapped_column(String(64), index=True)
    disclosure_budget_epoch: Mapped[int] = mapped_column(Integer, index=True)
    disclosure_policy_generation: Mapped[int] = mapped_column(Integer)
    context_json: Mapped[dict[str, object]] = mapped_column(JSON)
    initial_state: Mapped[str] = mapped_column(String(24))
    reason_code: Mapped[str] = mapped_column(String(120), default="")
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Phase1FactDisclosureAuthorizationFact(Base):
    __tablename__ = "phase1_fact_disclosure_authorization_facts"
    __table_args__ = (UniqueConstraint("authorization_id", "claim_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    authorization_id: Mapped[str] = mapped_column(
        ForeignKey("phase1_fact_disclosure_authorizations.id"), index=True
    )
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id"), index=True)


class Phase1FactDisclosureAuthorizationTaxonomy(Base):
    __tablename__ = "phase1_fact_disclosure_authorization_taxonomy"
    __table_args__ = (UniqueConstraint("authorization_id", "taxonomy_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    authorization_id: Mapped[str] = mapped_column(
        ForeignKey("phase1_fact_disclosure_authorizations.id"), index=True
    )
    taxonomy_id: Mapped[str] = mapped_column(String(120), index=True)


class Phase1FactDisclosureLifecycleEvent(Base):
    __tablename__ = "phase1_fact_disclosure_lifecycle_events"
    __table_args__ = (
        UniqueConstraint("authorization_id", "sequence"),
        CheckConstraint(
            "state IN ('authorized', 'consuming', 'validated_response', 'expired', "
            "'denied', 'failed', 'indeterminate', 'cancelled')",
            name="ck_phase1_fact_disclosure_lifecycle_state",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    authorization_id: Mapped[str] = mapped_column(
        ForeignKey("phase1_fact_disclosure_authorizations.id"), index=True
    )
    logical_payload_digest: Mapped[str] = mapped_column(String(64))
    sequence: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(24))
    reason_code: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Phase1FactDisclosureReleaseEvent(Base):
    __tablename__ = "phase1_fact_disclosure_release_events"
    __table_args__ = (UniqueConstraint("authorization_id", "sequence"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    authorization_id: Mapped[str] = mapped_column(
        ForeignKey("phase1_fact_disclosure_authorizations.id"), index=True
    )
    logical_payload_digest: Mapped[str] = mapped_column(String(64))
    release_fingerprint: Mapped[str] = mapped_column(String(64))
    sequence: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


Index(
    "uq_source_occurrence_null_safe_identity",
    SourceOccurrence.source_key,
    SourceOccurrence.subject_key,
    SourceOccurrence.employer_key,
    func.coalesce(SourceOccurrence.period_start, ""),
    func.coalesce(SourceOccurrence.period_end, ""),
    SourceOccurrence.statement_kind,
    SourceOccurrence.semantic_anchor,
    unique=True,
)
Index(
    "uq_search_profile_single_active",
    SearchProfileVersion.active,
    unique=True,
    sqlite_where=SearchProfileVersion.active.is_(True),
)
Index(
    "uq_claim_revision_null_safe_identity",
    ClaimRevision.claim_id,
    ClaimRevision.semantic_value,
    ClaimRevision.employer_key,
    func.coalesce(ClaimRevision.period_start, ""),
    func.coalesce(ClaimRevision.period_end, ""),
    unique=True,
)
