import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from job_search_cockpit.facts.conflicts import classify_risks
from job_search_cockpit.facts.types import RiskFlag, Sensitivity
from job_search_cockpit.imports.types import CandidateClaim, EvidenceRef
from job_search_cockpit.storage.models import (
    AuditEvent,
    Claim,
    ClaimRevision,
    ClaimStatus,
    ClaimSupportAssertion,
    ConfidentialPermissionEvent,
    ConflictGroup,
    ConflictMember,
    Decision,
)
from job_search_cockpit.storage.mutation import MutationCoordinator


class ReviewError(ValueError):
    """Base error for an invalid fact-review command."""


class ClaimVersionConflict(ReviewError):
    """Raised when a review form is stale."""


class IndividualReviewRequired(ReviewError):
    """Raised when a risky fact is submitted through bulk review."""


@dataclass(frozen=True, slots=True)
class BulkReviewItem:
    claim_id: str
    revision_id: str
    expected_version: int


@dataclass(frozen=True, slots=True)
class BulkReviewResult:
    approved_claim_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClaimView:
    id: str
    canonical_key: str
    status: ClaimStatus
    sensitivity: Sensitivity
    active_revision_id: str
    version: int
    stale: bool


@dataclass(frozen=True, slots=True)
class EligibilityResult:
    allowed: bool
    reason: str


class AttributionPolicy:
    @staticmethod
    def validate(
        claim: Claim,
        revision: ClaimRevision,
        support: ClaimSupportAssertion,
    ) -> EligibilityResult:
        employment = claim.canonical_key.startswith("employment.")
        category = claim.category.casefold()
        quantified_work = category in {
            "achievement",
            "metric",
            "metrics",
            "responsibility",
            "responsibilities",
            "team_scope",
        } or claim.canonical_key.startswith(("metric.", "team_scope."))
        requires_employer = employment or quantified_work or category in {"title", "dates"}
        requires_period = quantified_work or (
            employment
            and category
            in {"achievement", "responsibility", "responsibilities", "team_scope"}
        )
        if requires_employer and not revision.employer_key:
            return EligibilityResult(False, "The fact has no verified employer attribution.")
        if requires_period and revision.period_start is None:
            return EligibilityResult(False, "The fact has no verified career period.")
        if requires_employer and support.employer_key != revision.employer_key:
            return EligibilityResult(False, "The supporting evidence names a different employer.")
        if requires_period and (
            support.period_start != revision.period_start
            or support.period_end != revision.period_end
        ):
            return EligibilityResult(False, "The supporting evidence covers a different period.")
        return EligibilityResult(True, "Attribution is valid.")


def _view(claim: Claim) -> ClaimView:
    if claim.active_revision_id is None:
        raise ReviewError("The claim has no active revision.")
    return ClaimView(
        claim.id,
        claim.canonical_key,
        claim.status,
        claim.sensitivity,
        claim.active_revision_id,
        claim.version,
        claim.stale,
    )


def _load_claim(session: Session, claim_id: str, expected_version: int) -> Claim:
    claim = session.get(Claim, claim_id)
    if claim is None:
        raise ReviewError("The fact does not exist.")
    if claim.version != expected_version:
        raise ClaimVersionConflict("This fact changed in another action.")
    return claim


def _open_conflict(session: Session, claim_id: str, revision_id: str | None = None) -> bool:
    statement = (
        select(ConflictMember.id)
        .join(ConflictGroup, ConflictMember.conflict_group_id == ConflictGroup.id)
        .where(ConflictMember.claim_id == claim_id, ConflictGroup.status == "open")
    )
    if revision_id is not None:
        statement = statement.where(ConflictMember.revision_id == revision_id)
    return session.scalar(statement) is not None


def _candidate_for_risk(claim: Claim, revision: ClaimRevision) -> CandidateClaim:
    return CandidateClaim(
        canonical_key=claim.canonical_key,
        category=claim.category,
        subject=claim.subject,
        value=revision.value_json,
        display_value=revision.display_value,
        evidence=EvidenceRef("stored", Path("stored"), "", "", ""),
        employer_key=revision.employer_key or None,
        period_start=revision.period_start,
        period_end=revision.period_end,
        semantic_family=claim.canonical_key,
        declared_risks=(
            frozenset({RiskFlag.POTENTIALLY_CONFIDENTIAL})
            if claim.sensitivity is not Sensitivity.NORMAL
            else frozenset()
        ),
    )


def _record_decision(
    session: Session,
    claim: Claim,
    revision_id: str | None,
    action: str,
    previous_version: int,
    reason: str,
    supersedes_decision_id: str | None = None,
) -> None:
    decision_id = str(uuid4())
    session.add(
        Decision(
            id=decision_id,
            claim_id=claim.id,
            revision_id=revision_id,
            action=action,
            status=claim.status.value,
            sensitivity=claim.sensitivity.value,
            actor="Varun",
            reason=reason,
            expected_claim_version=previous_version,
            supersedes_decision_id=supersedes_decision_id,
        )
    )
    session.add(
        AuditEvent(
            id=str(uuid4()),
            event_type=f"fact_{action}",
            area="facts",
            subject_id=claim.id,
            summary=f"Fact review action recorded: {action.replace('_', ' ')}.",
            after_json={
                "decision_id": decision_id,
                "status": claim.status.value,
                "sensitivity": claim.sensitivity.value,
                "version": claim.version,
            },
            sensitive=claim.sensitivity is Sensitivity.CONFIDENTIAL,
            reason=reason,
        )
    )


class ReviewService:
    def __init__(self, coordinator: MutationCoordinator) -> None:
        self.coordinator = coordinator

    def approve(
        self,
        claim_id: str,
        revision_id: str,
        expected_version: int,
        reason: str = "",
    ) -> ClaimView:
        def approve_one(session: Session) -> ClaimView:
            claim = _load_claim(session, claim_id, expected_version)
            revision = session.get(ClaimRevision, revision_id)
            if revision is None or revision.claim_id != claim.id:
                raise ReviewError("The selected revision does not belong to this fact.")
            if _open_conflict(session, claim.id):
                raise IndividualReviewRequired("Resolve the source conflict explicitly first.")
            previous_version = claim.version
            claim.active_revision_id = revision.id
            claim.status = ClaimStatus.APPROVED
            claim.version += 1
            _record_decision(session, claim, revision.id, "approve", previous_version, reason)
            return _view(claim)

        return self.coordinator.run(approve_one, "approve_fact", expected_version)

    def correct(
        self,
        claim_id: str,
        value: dict[str, object],
        display_value: str,
        employer_key: str | None,
        period_start: date | None,
        period_end: date | None,
        expected_version: int,
        reason: str,
    ) -> ClaimView:
        if not display_value.strip() or not reason.strip():
            raise ReviewError("Corrected wording and a reason are required.")

        def correct_one(session: Session) -> ClaimView:
            claim = _load_claim(session, claim_id, expected_version)
            if _open_conflict(session, claim.id):
                raise IndividualReviewRequired(
                    "Resolve the source conflict explicitly instead of correcting this fact."
                )
            previous_version = claim.version
            revision = ClaimRevision(
                id=str(uuid4()),
                claim_id=claim.id,
                value_json=value,
                display_value=display_value.strip(),
                semantic_value=json.dumps(value, sort_keys=True, separators=(",", ":")),
                origin="user",
                employer_key=employer_key or "",
                period_start=period_start,
                period_end=period_end,
            )
            session.add(revision)
            session.flush()
            claim.active_revision_id = revision.id
            claim.status = ClaimStatus.CORRECTED
            claim.version += 1
            _record_decision(
                session, claim, revision.id, "correct", previous_version, reason.strip()
            )
            return _view(claim)

        return self.coordinator.run(correct_one, "correct_fact", expected_version)

    def confirm_corrected_support(
        self,
        claim_id: str,
        revision_id: str,
        expected_version: int,
        actor: str,
        confirmation: str,
        reason: str,
    ) -> ClaimView:
        if confirmation != "CONFIRM CORRECTED FACT SUPPORT":
            raise ReviewError("Type the exact support confirmation phrase.")
        if not reason.strip():
            raise ReviewError("A support reason is required.")

        def confirm(session: Session) -> ClaimView:
            claim = _load_claim(session, claim_id, expected_version)
            revision = session.get(ClaimRevision, revision_id)
            if (
                revision is None
                or revision.claim_id != claim.id
                or revision.origin != "user"
                or claim.active_revision_id != revision.id
            ):
                raise ReviewError("Only the exact active corrected revision can be confirmed.")
            previous_version = claim.version
            session.add(
                ClaimSupportAssertion(
                    id=str(uuid4()),
                    claim_id=claim.id,
                    revision_id=revision.id,
                    support_state="supported",
                    support_type="user_confirmed",
                    source_evidence_id=None,
                    employer_key=revision.employer_key,
                    period_start=revision.period_start,
                    period_end=revision.period_end,
                    actor=actor,
                    reason=reason.strip(),
                )
            )
            claim.version += 1
            _record_decision(
                session,
                claim,
                revision.id,
                "confirm_support",
                previous_version,
                reason.strip(),
            )
            return _view(claim)

        return self.coordinator.run(confirm, "confirm_corrected_support", expected_version)

    def reject(self, claim_id: str, expected_version: int, reason: str) -> ClaimView:
        if not reason.strip():
            raise ReviewError("A rejection reason is required.")

        def reject_one(session: Session) -> ClaimView:
            claim = _load_claim(session, claim_id, expected_version)
            previous_version = claim.version
            claim.status = ClaimStatus.REJECTED
            claim.version += 1
            _record_decision(
                session, claim, claim.active_revision_id, "reject", previous_version, reason.strip()
            )
            return _view(claim)

        return self.coordinator.run(reject_one, "reject_fact", expected_version)

    def revert(
        self,
        claim_id: str,
        target_decision_id: str,
        expected_version: int,
        reason: str,
    ) -> ClaimView:
        if not reason.strip():
            raise ReviewError("A revert reason is required.")

        def revert_one(session: Session) -> ClaimView:
            claim = _load_claim(session, claim_id, expected_version)
            target = session.get(Decision, target_decision_id)
            if target is None or target.claim_id != claim.id:
                raise ReviewError("The decision to revert does not belong to this fact.")
            previous_version = claim.version
            claim.status = ClaimStatus.UNRESOLVED
            claim.version += 1
            _record_decision(
                session,
                claim,
                claim.active_revision_id,
                "revert",
                previous_version,
                reason.strip(),
                target.id,
            )
            return _view(claim)

        return self.coordinator.run(revert_one, "revert_fact", expected_version)

    def set_sensitivity(
        self,
        claim_id: str,
        sensitivity: Sensitivity,
        expected_version: int,
        reason: str = "",
    ) -> ClaimView:
        if sensitivity is Sensitivity.UNREVIEWED:
            raise ReviewError("Choose normal or confidential sensitivity.")

        def set_one(session: Session) -> ClaimView:
            claim = _load_claim(session, claim_id, expected_version)
            previous_version = claim.version
            claim.sensitivity = sensitivity
            claim.version += 1
            _record_decision(
                session,
                claim,
                claim.active_revision_id,
                "set_sensitivity",
                previous_version,
                reason,
            )
            return _view(claim)

        return self.coordinator.run(set_one, "set_fact_sensitivity", expected_version)

    def bulk_approve_low_risk(self, items: Sequence[BulkReviewItem]) -> BulkReviewResult:
        if not items:
            raise ReviewError("Select at least one fact.")

        def approve_batch(session: Session) -> BulkReviewResult:
            loaded: list[tuple[Claim, ClaimRevision, BulkReviewItem]] = []
            for item in items:
                claim = _load_claim(session, item.claim_id, item.expected_version)
                revision = session.get(ClaimRevision, item.revision_id)
                if revision is None or revision.claim_id != claim.id:
                    raise ReviewError("A selected revision does not belong to its fact.")
                risks = classify_risks(_candidate_for_risk(claim, revision))
                if risks or _open_conflict(session, claim.id) or claim.stale:
                    raise IndividualReviewRequired("A selected fact requires individual review.")
                loaded.append((claim, revision, item))
            approved: list[str] = []
            for claim, revision, item in loaded:
                claim.active_revision_id = revision.id
                claim.status = ClaimStatus.APPROVED
                claim.version += 1
                _record_decision(
                    session, claim, revision.id, "approve", item.expected_version, "Bulk approval"
                )
                approved.append(claim.id)
            return BulkReviewResult(tuple(approved))

        return self.coordinator.run(approve_batch, "bulk_approve_facts", expected_version=None)


def is_resume_eligible(
    session: Session,
    claim_id: str,
    revision_id: str,
    named_use_id: str,
    permission_event_id: str | None = None,
) -> EligibilityResult:
    claim = session.get(Claim, claim_id)
    revision = session.get(ClaimRevision, revision_id)
    if claim is None or revision is None or revision.claim_id != claim.id:
        return EligibilityResult(False, "The fact or revision does not exist.")
    if claim.active_revision_id != revision.id:
        return EligibilityResult(False, "Only the active fact revision can be used.")
    if claim.status not in {ClaimStatus.APPROVED, ClaimStatus.CORRECTED}:
        return EligibilityResult(False, "The fact is not approved.")
    if claim.stale:
        return EligibilityResult(False, "The fact is stale after the latest import.")
    support = session.scalar(
        select(ClaimSupportAssertion)
        .where(
            ClaimSupportAssertion.claim_id == claim.id,
            ClaimSupportAssertion.revision_id == revision.id,
        )
        .order_by(ClaimSupportAssertion.created_at.desc())
    )
    if support is None or support.support_state != "supported":
        return EligibilityResult(False, "The active revision has no current supporting evidence.")
    attribution = AttributionPolicy.validate(claim, revision, support)
    if not attribution.allowed:
        return attribution
    if _open_conflict(session, claim.id):
        return EligibilityResult(False, "The fact belongs to an unresolved source conflict.")
    if claim.sensitivity is Sensitivity.UNREVIEWED:
        return EligibilityResult(False, "The fact's confidentiality has not been reviewed.")
    if claim.sensitivity is Sensitivity.NORMAL:
        return EligibilityResult(True, "The approved fact is eligible for this use.")
    if permission_event_id is None:
        return EligibilityResult(
            False, "Approved but confidential; explicit permission is required."
        )
    permission = session.get(ConfidentialPermissionEvent, permission_event_id)
    if (
        permission is None
        or permission.claim_id != claim.id
        or permission.revision_id != revision.id
        or permission.named_use_id != named_use_id
    ):
        return EligibilityResult(False, "The confidential-use permission does not match.")
    latest = session.scalar(
        select(ConfidentialPermissionEvent)
        .where(ConfidentialPermissionEvent.permission_id == permission.permission_id)
        .order_by(ConfidentialPermissionEvent.event_version.desc())
    )
    if (
        latest is None
        or latest.id != permission.id
        or latest.event_type not in {"grant", "supersede"}
    ):
        return EligibilityResult(False, "The confidential-use permission is no longer active.")
    if latest.expires_at is not None:
        expires_at = latest.expires_at
        if expires_at.tzinfo is None:
            from datetime import UTC

            expires_at = expires_at.replace(tzinfo=UTC)
        from datetime import UTC, datetime

        if expires_at <= datetime.now(UTC):
            return EligibilityResult(False, "The confidential-use permission has expired.")
    return EligibilityResult(True, "The exact confidential-use permission is active.")
