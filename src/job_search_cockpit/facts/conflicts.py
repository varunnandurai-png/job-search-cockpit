import json
import re
from dataclasses import dataclass
from datetime import date
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from job_search_cockpit.facts.types import RiskFlag
from job_search_cockpit.imports.grammar import normalize_text, semantic_anchor
from job_search_cockpit.imports.types import CandidateClaim
from job_search_cockpit.storage.models import (
    AuditEvent,
    Claim,
    ClaimRevision,
    ClaimStatus,
    ConflictGroup,
    ConflictMember,
    ConflictResolution,
    Decision,
    ImportRunOccurrence,
)
from job_search_cockpit.storage.mutation import MutationCoordinator

_QUANTIFIED = re.compile(
    r"(?i)(?:[$₹€£]|\b(?:usd|inr|sgd)\b)?\s*\d[\d,.]*(?:\s*[-\u2013\u2014]\s*\d[\d,.]*)?"
    r"\s*(?:%|[kmb]\+?|\+)?"
)
_DATE = re.compile(
    r"(?i)\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r"\s+\d{4}\b"
)


@dataclass(frozen=True, slots=True)
class ConflictPreviewGroup:
    semantic_family: str
    members: tuple[CandidateClaim, ...]


@dataclass(frozen=True, slots=True)
class ConflictPreview:
    groups: tuple[ConflictPreviewGroup, ...]

    @property
    def count(self) -> int:
        return len(self.groups)


@dataclass(frozen=True, slots=True)
class ConflictSummary:
    open_groups: int
    reopened_groups: int


@dataclass(frozen=True, slots=True)
class ResolveConflictCommand:
    group_id: str
    selected_revision_id: str | None
    corrected_value: dict[str, object] | None
    corrected_display_value: str | None
    expected_group_version: int
    reason: str
    employer_key: str | None
    period_start: date | None
    period_end: date | None


@dataclass(frozen=True, slots=True)
class ConflictResolutionView:
    group_id: str
    resolution_id: str
    status: str
    version: int
    selected_revision_id: str | None
    corrected_revision_id: str | None


class ConflictResolutionError(ValueError):
    """Raised when a conflict command is invalid or stale."""


def classify_risks(candidate: CandidateClaim) -> frozenset[RiskFlag]:
    risks = set(candidate.declared_risks)
    key = candidate.canonical_key.lower()
    category = candidate.category.lower()
    display = candidate.display_value
    if _QUANTIFIED.search(display):
        risks.add(RiskFlag.QUANTIFIED)
    if category == "dates" or key.endswith(".dates") or _DATE.search(display):
        risks.add(RiskFlag.DATE)
    if category == "title" or key.endswith(".title"):
        risks.add(RiskFlag.TITLE)
    if "team" in key or re.search(r"\b(?:scrum\s+)?teams?\b", display, re.IGNORECASE):
        risks.add(RiskFlag.TEAM_SCOPE)
    return frozenset(risks)


def normalize_for_comparison(candidate: CandidateClaim) -> str:
    return _normalize_value_for_comparison(candidate.display_value)


def _normalize_value_for_comparison(value: str) -> str:
    normalized = normalize_text(value).casefold()
    normalized = re.sub(r"\s*[-\u2013\u2014]\s*", "-", normalized)
    normalized = re.sub(r"[^a-z0-9%+.-]+", " ", normalized)
    return " ".join(normalized.split())


def analyze_candidate_conflicts(candidates: tuple[CandidateClaim, ...]) -> ConflictPreview:
    families: dict[tuple[str, str, date | None, date | None], list[CandidateClaim]] = {}
    for candidate in candidates:
        key = (
            candidate.semantic_family,
            candidate.employer_key or "",
            candidate.period_start,
            candidate.period_end,
        )
        families.setdefault(key, []).append(candidate)
    groups = [
        ConflictPreviewGroup(key[0], tuple(members))
        for key, members in families.items()
        if len({normalize_for_comparison(member) for member in members}) > 1
    ]
    groups.sort(key=lambda group: group.semantic_family)
    return ConflictPreview(tuple(groups))


def _stored_family(claim: Claim, revision: ClaimRevision) -> str:
    canonical = claim.canonical_key
    lowered = revision.display_value.lower()
    if canonical == "profile.product_years":
        return canonical
    if canonical.endswith(".title"):
        return f"employment.title.{revision.employer_key}"
    if canonical.endswith(".dates"):
        return f"employment.dates.{revision.employer_key}"
    if re.search(r"\b\d+\s+(?:scrum\s+)?teams?\b", lowered):
        return f"team_scope.{revision.employer_key}"
    if claim.category.casefold() == "achievement" and _QUANTIFIED.search(revision.display_value):
        anchor = semantic_anchor(revision.display_value)
        if anchor != "statement":
            return f"metric.{anchor}"
    return canonical


def rebuild_conflicts(
    session: Session,
    import_run_id: str,
    *,
    close_obsolete: bool = True,
) -> ConflictSummary:
    rows = session.execute(
        select(Claim, ClaimRevision)
        .join(ImportRunOccurrence, ImportRunOccurrence.claim_id == Claim.id)
        .join(ClaimRevision, ImportRunOccurrence.revision_id == ClaimRevision.id)
        .where(ImportRunOccurrence.import_run_id == import_run_id)
    ).all()
    families: dict[
        tuple[str, str, date | None, date | None], list[tuple[Claim, ClaimRevision]]
    ] = {}
    for claim, revision in rows:
        key = (
            _stored_family(claim, revision),
            revision.employer_key,
            revision.period_start,
            revision.period_end,
        )
        families.setdefault(key, []).append((claim, revision))

    open_count = 0
    reopened_count = 0
    active_group_ids: set[str] = set()
    for (family, employer, period_start, period_end), members in families.items():
        normalized_values = {
            _normalize_value_for_comparison(revision.display_value) for _, revision in members
        }
        if len(normalized_values) <= 1:
            continue
        group = session.scalar(
            select(ConflictGroup).where(
                ConflictGroup.semantic_family == family,
                ConflictGroup.employer_key == employer,
                ConflictGroup.period_start == period_start,
                ConflictGroup.period_end == period_end,
            )
        )
        if group is None:
            group = ConflictGroup(
                id=str(uuid4()),
                semantic_family=family,
                employer_key=employer,
                period_start=period_start,
                period_end=period_end,
                status="open",
                version=1,
            )
            session.add(group)
            session.flush()
        active_group_ids.add(group.id)
        existing_revision_ids = set(
            session.scalars(
                select(ConflictMember.revision_id).where(
                    ConflictMember.conflict_group_id == group.id
                )
            )
        )
        incoming_revision_ids = {revision.id for _, revision in members}
        evidence_changed = incoming_revision_ids != existing_revision_ids
        if group.status == "resolved" and evidence_changed:
            previous_version = group.version
            group.status = "open"
            group.version += 1
            session.add(
                ConflictResolution(
                    id=str(uuid4()),
                    conflict_group_id=group.id,
                    resolution_type="reopened",
                    selected_revision_id=None,
                    corrected_revision_id=None,
                    expected_group_version=previous_version,
                    reason="Changed source evidence reopened this conflict",
                    employer_key=employer,
                    period_start=period_start,
                    period_end=period_end,
                )
            )
            reopened_count += 1
        elif group.status == "resolved":
            continue
        for claim, revision in members:
            exists = session.scalar(
                select(ConflictMember.id).where(
                    ConflictMember.conflict_group_id == group.id,
                    ConflictMember.revision_id == revision.id,
                )
            )
            if exists is None:
                session.add(
                    ConflictMember(
                        id=str(uuid4()),
                        conflict_group_id=group.id,
                        claim_id=claim.id,
                        revision_id=revision.id,
                    )
                )
        open_count += 1

    obsolete = (
        tuple(session.scalars(select(ConflictGroup).where(ConflictGroup.status == "open")))
        if close_obsolete
        else ()
    )
    for group in obsolete:
        if group.id in active_group_ids:
            continue
        previous_version = group.version
        group.status = "resolved"
        group.version += 1
        session.add(
            ConflictResolution(
                id=str(uuid4()),
                conflict_group_id=group.id,
                resolution_type="closed",
                selected_revision_id=None,
                corrected_revision_id=None,
                expected_group_version=previous_version,
                reason="Current curated sources no longer disagree",
                employer_key=group.employer_key,
                period_start=group.period_start,
                period_end=group.period_end,
            )
        )
    return ConflictSummary(open_count, reopened_count)


def resolve_conflict(
    coordinator: MutationCoordinator,
    command: ResolveConflictCommand,
) -> ConflictResolutionView:
    has_selected = command.selected_revision_id is not None
    has_correction = command.corrected_value is not None
    if has_selected == has_correction:
        raise ConflictResolutionError("Select one source revision or provide one correction.")
    if not command.reason.strip():
        raise ConflictResolutionError("A reason is required to resolve a conflict.")

    def resolve(session: Session) -> ConflictResolutionView:
        group = session.get(ConflictGroup, command.group_id)
        if group is None or group.status != "open":
            raise ConflictResolutionError("This conflict is not open.")
        if group.version != command.expected_group_version:
            raise ConflictResolutionError("This conflict changed. Review every source again.")
        members = session.scalars(
            select(ConflictMember).where(ConflictMember.conflict_group_id == group.id)
        ).all()
        if not members:
            raise ConflictResolutionError("This conflict has no source revisions.")

        selected_revision_id = command.selected_revision_id
        corrected_revision_id: str | None = None
        if selected_revision_id is not None:
            member = next(
                (item for item in members if item.revision_id == selected_revision_id),
                None,
            )
            if member is None:
                raise ConflictResolutionError("The selected revision is not part of this conflict.")
            claim = session.get(Claim, member.claim_id)
            revision = session.get(ClaimRevision, selected_revision_id)
            if claim is None or revision is None:
                raise ConflictResolutionError("The selected source revision is unavailable.")
            claim.active_revision_id = revision.id
            claim.status = ClaimStatus.APPROVED
        else:
            if command.corrected_display_value is None:
                raise ConflictResolutionError("Corrected wording is required.")
            base_member = members[0]
            claim = session.get(Claim, base_member.claim_id)
            if claim is None:
                raise ConflictResolutionError("The conflict claim is unavailable.")
            semantic_value = json.dumps(
                command.corrected_value, sort_keys=True, separators=(",", ":")
            )
            revision = ClaimRevision(
                id=str(uuid4()),
                claim_id=claim.id,
                value_json=command.corrected_value or {},
                display_value=command.corrected_display_value,
                semantic_value=semantic_value,
                origin="user",
                employer_key=command.employer_key or "",
                period_start=command.period_start,
                period_end=command.period_end,
            )
            session.add(revision)
            session.flush()
            corrected_revision_id = revision.id
            claim.active_revision_id = revision.id
            claim.status = ClaimStatus.CORRECTED

        previous_claim_version = claim.version
        claim.version += 1
        group.status = "resolved"
        group.version += 1
        resolution_id = str(uuid4())
        session.add(
            ConflictResolution(
                id=resolution_id,
                conflict_group_id=group.id,
                resolution_type="selected" if has_selected else "corrected",
                selected_revision_id=selected_revision_id,
                corrected_revision_id=corrected_revision_id,
                expected_group_version=command.expected_group_version,
                reason=command.reason.strip(),
                employer_key=command.employer_key or "",
                period_start=command.period_start,
                period_end=command.period_end,
            )
        )
        decision_id = str(uuid4())
        session.add(
            Decision(
                id=decision_id,
                claim_id=claim.id,
                revision_id=claim.active_revision_id,
                action="resolve_conflict",
                status=claim.status.value,
                sensitivity=claim.sensitivity.value,
                actor="Varun",
                reason=command.reason.strip(),
                expected_claim_version=previous_claim_version,
            )
        )
        session.add(
            AuditEvent(
                id=str(uuid4()),
                event_type="conflict_resolved",
                area="facts",
                subject_id=group.id,
                summary="A source conflict was resolved explicitly.",
                after_json={"resolution_id": resolution_id, "group_version": group.version},
                reason=command.reason.strip(),
            )
        )
        return ConflictResolutionView(
            group.id,
            resolution_id,
            group.status,
            group.version,
            selected_revision_id,
            corrected_revision_id,
        )

    return coordinator.run(
        resolve,
        "resolve_conflict",
        expected_version=command.expected_group_version,
    )
