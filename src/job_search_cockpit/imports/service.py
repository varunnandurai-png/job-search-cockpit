import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from job_search_cockpit.config import Settings, SourceKind, SourceSpec
from job_search_cockpit.facts.conflicts import analyze_candidate_conflicts
from job_search_cockpit.facts.types import RiskFlag, Sensitivity
from job_search_cockpit.imports.assessment import AssessmentImporter
from job_search_cockpit.imports.master_profile import MasterProfileImporter
from job_search_cockpit.imports.profile_json import ProfileJsonImporter
from job_search_cockpit.imports.types import (
    CandidateClaim,
    ImportResult,
    MalformedSourceError,
    SourceImporter,
)
from job_search_cockpit.imports.workflow import WorkflowImporter
from job_search_cockpit.sources import UnsafeSourceError, safe_open_source
from job_search_cockpit.storage.models import (
    Claim,
    ClaimEvidence,
    ClaimRevision,
    ClaimStatus,
    ClaimSupportAssertion,
    ImportAttempt,
    ImportRun,
    ImportRunOccurrence,
    ImportRunSource,
    SourceDocument,
    SourceOccurrence,
)
from job_search_cockpit.storage.mutation import MutationCoordinator
from job_search_cockpit.storage.recovery_ledger import RecoveryEvent

MANIFEST_VERSION = "phase1.v1"


class PreviewRejected(RuntimeError):
    """Raised when an import preview is no longer safe to apply."""


@dataclass(frozen=True, slots=True)
class SourceStatus:
    source_key: str
    status: str
    content_hash: str | None
    message: str = ""


@dataclass(frozen=True, slots=True)
class ImportPreview:
    id: str
    session_id: str
    manifest_version: str
    source_statuses: tuple[SourceStatus, ...]
    candidate_digest: str
    candidate_count: int
    conflict_count: int
    created_at: datetime
    expires_at: datetime
    incomplete: bool


@dataclass(frozen=True, slots=True)
class AppliedImport:
    run_id: str
    attempt_id: str
    created_claims: int
    created_revisions: int
    changed_claims: tuple[str, ...]
    stale_claims: tuple[str, ...]
    source_statuses: tuple[SourceStatus, ...]


@dataclass(slots=True)
class _PreviewSnapshot:
    preview: ImportPreview
    results: tuple[ImportResult, ...]
    candidates: tuple[CandidateClaim, ...]
    deadline_monotonic: float
    used: bool = False


def _candidate_digest(candidates: tuple[CandidateClaim, ...]) -> str:
    payload = [
        {
            "canonical_key": candidate.canonical_key,
            "value": candidate.value,
            "employer_key": candidate.employer_key,
            "period_start": candidate.period_start.isoformat() if candidate.period_start else None,
            "period_end": candidate.period_end.isoformat() if candidate.period_end else None,
            "semantic_family": candidate.semantic_family,
            "source_key": candidate.evidence.source_key,
            "source_hash": candidate.evidence.source_hash,
            "locator": candidate.evidence.locator,
        }
        for candidate in candidates
    ]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return sha256(canonical).hexdigest()


class ImportService:
    def __init__(
        self,
        settings: Settings,
        coordinator: MutationCoordinator,
        *,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings = settings
        self.coordinator = coordinator
        self._monotonic_clock = monotonic_clock
        self._previews: dict[str, _PreviewSnapshot] = {}
        self._preview_lock = threading.Lock()
        self._importers: dict[SourceKind, SourceImporter] = {
            SourceKind.ASSESSMENT: AssessmentImporter(),
            SourceKind.PROFILE_JSON: ProfileJsonImporter(),
            SourceKind.MASTER_PROFILE: MasterProfileImporter(),
            SourceKind.RESUME_WORKFLOW: WorkflowImporter(),
        }

    def _read(self, spec: SourceSpec) -> tuple[SourceStatus, ImportResult | None]:
        if not spec.path.exists():
            return SourceStatus(spec.key, "missing", None, "Source file is missing."), None
        try:
            result = self._importers[spec.kind].read(spec)
            return SourceStatus(spec.key, "ready", result.source_hash), result
        except MalformedSourceError as error:
            return SourceStatus(spec.key, "malformed", None, str(error)), None
        except (OSError, UnsafeSourceError) as error:
            return SourceStatus(spec.key, "unreadable", None, type(error).__name__), None

    def preview(self, session_id: str, now: datetime) -> ImportPreview:
        statuses: list[SourceStatus] = []
        results: list[ImportResult] = []
        for spec in self.settings.sources:
            status, result = self._read(spec)
            statuses.append(status)
            if result is not None:
                results.append(result)
        candidates = tuple(claim for result in results for claim in result.claims)
        digest = _candidate_digest(candidates)
        preview = ImportPreview(
            id=str(uuid4()),
            session_id=session_id,
            manifest_version=MANIFEST_VERSION,
            source_statuses=tuple(statuses),
            candidate_digest=digest,
            candidate_count=len(candidates),
            conflict_count=analyze_candidate_conflicts(candidates).count,
            created_at=now,
            expires_at=now + timedelta(minutes=10),
            incomplete=any(status.status != "ready" for status in statuses),
        )
        with self._preview_lock:
            self._previews[preview.id] = _PreviewSnapshot(
                preview,
                tuple(results),
                candidates,
                self._monotonic_clock() + 600.0,
            )
        return preview

    def _consume_preview(self, preview_id: str, session_id: str) -> _PreviewSnapshot:
        with self._preview_lock:
            snapshot = self._previews.get(preview_id)
            if snapshot is None:
                raise PreviewRejected("This import preview is unavailable after restart.")
            if snapshot.used:
                raise PreviewRejected("This import preview was already used.")
            if snapshot.preview.session_id != session_id:
                raise PreviewRejected("This import preview belongs to a different session.")
            if snapshot.preview.manifest_version != MANIFEST_VERSION:
                raise PreviewRejected("The import manifest changed. Create a new preview.")
            if self._monotonic_clock() >= snapshot.deadline_monotonic:
                snapshot.used = True
                raise PreviewRejected("This import preview expired. Create a new preview.")
            snapshot.used = True
            return snapshot

    def _revalidate_sources(self, snapshot: _PreviewSnapshot) -> None:
        expected = {status.source_key: status for status in snapshot.preview.source_statuses}
        for spec in self.settings.sources:
            status = expected[spec.key]
            if status.status == "ready":
                try:
                    opened = safe_open_source(spec)
                except (OSError, UnsafeSourceError) as error:
                    raise PreviewRejected(f"Source {spec.key} changed after preview.") from error
                if opened.content_hash != status.content_hash:
                    raise PreviewRejected(f"Source {spec.key} changed after preview.")
            elif status.status == "malformed":
                raise PreviewRejected(
                    f"Source {spec.key} is malformed and cannot be partially imported."
                )
            else:
                current, _result = self._read(spec)
                if current.status != status.status or current.message != status.message:
                    raise PreviewRejected(f"Source {spec.key} changed after preview.")

    @staticmethod
    def _find_or_create_document(session: Session, candidate: CandidateClaim) -> SourceDocument:
        path = str(candidate.evidence.source_path)
        document = session.scalar(
            select(SourceDocument).where(
                SourceDocument.path == path,
                SourceDocument.content_hash == candidate.evidence.source_hash,
            )
        )
        if document is not None:
            return document
        source_stat = candidate.evidence.source_path.stat()
        document = SourceDocument(
            id=str(uuid4()),
            source_key=candidate.evidence.source_key,
            path=path,
            content_hash=candidate.evidence.source_hash,
            size=source_stat.st_size,
            modified_ns=source_stat.st_mtime_ns,
        )
        session.add(document)
        session.flush()
        return document

    @staticmethod
    def _find_or_create_occurrence(session: Session, candidate: CandidateClaim) -> SourceOccurrence:
        subject_key = candidate.subject.casefold().strip()
        employer_key = candidate.employer_key or ""
        semantic_anchor = candidate.canonical_key.rsplit(".", 1)[-1]
        occurrence = session.scalar(
            select(SourceOccurrence).where(
                SourceOccurrence.source_key == candidate.evidence.source_key,
                SourceOccurrence.subject_key == subject_key,
                SourceOccurrence.employer_key == employer_key,
                SourceOccurrence.period_start == candidate.period_start,
                SourceOccurrence.period_end == candidate.period_end,
                SourceOccurrence.statement_kind == candidate.category,
                SourceOccurrence.semantic_anchor == semantic_anchor,
            )
        )
        if occurrence is not None:
            return occurrence
        occurrence = SourceOccurrence(
            id=str(uuid4()),
            source_key=candidate.evidence.source_key,
            subject_key=subject_key,
            employer_key=employer_key,
            period_start=candidate.period_start,
            period_end=candidate.period_end,
            statement_kind=candidate.category,
            semantic_anchor=semantic_anchor,
        )
        session.add(occurrence)
        session.flush()
        return occurrence

    @staticmethod
    def _upsert_candidate(
        session: Session, candidate: CandidateClaim
    ) -> tuple[Claim, ClaimRevision, bool, bool]:
        claim = session.scalar(select(Claim).where(Claim.canonical_key == candidate.canonical_key))
        created_claim = claim is None
        if claim is None:
            sensitivity = (
                Sensitivity.UNREVIEWED
                if RiskFlag.POTENTIALLY_CONFIDENTIAL in candidate.declared_risks
                else Sensitivity.NORMAL
            )
            claim = Claim(
                id=str(uuid4()),
                canonical_key=candidate.canonical_key,
                category=candidate.category,
                subject=candidate.subject,
                status=ClaimStatus.UNRESOLVED,
                sensitivity=sensitivity,
                stale=False,
                version=1,
            )
            session.add(claim)
            session.flush()
        semantic_value = json.dumps(candidate.value, sort_keys=True, separators=(",", ":"))
        employer_key = candidate.employer_key or ""
        revision = session.scalar(
            select(ClaimRevision).where(
                ClaimRevision.claim_id == claim.id,
                ClaimRevision.semantic_value == semantic_value,
                ClaimRevision.employer_key == employer_key,
                ClaimRevision.period_start == candidate.period_start,
                ClaimRevision.period_end == candidate.period_end,
            )
        )
        created_revision = revision is None
        changed = False
        if revision is None:
            revision = ClaimRevision(
                id=str(uuid4()),
                claim_id=claim.id,
                value_json=candidate.value,
                display_value=candidate.display_value,
                semantic_value=semantic_value,
                origin="source",
                employer_key=employer_key,
                period_start=candidate.period_start,
                period_end=candidate.period_end,
            )
            session.add(revision)
            session.flush()
        if claim.active_revision_id != revision.id:
            changed = claim.active_revision_id is not None
            claim.active_revision_id = revision.id
            claim.status = ClaimStatus.UNRESOLVED
            claim.stale = False
            claim.version += int(changed)
            if RiskFlag.POTENTIALLY_CONFIDENTIAL in candidate.declared_risks:
                claim.sensitivity = Sensitivity.UNREVIEWED
        elif claim.stale:
            claim.stale = False
            if claim.status in {ClaimStatus.APPROVED, ClaimStatus.CORRECTED}:
                claim.status = ClaimStatus.UNRESOLVED
            claim.version += 1
        return claim, revision, created_claim, created_revision

    @staticmethod
    def _attach_evidence_and_support(
        session: Session,
        candidate: CandidateClaim,
        claim: Claim,
        revision: ClaimRevision,
        document: SourceDocument,
        occurrence: SourceOccurrence,
    ) -> None:
        evidence_row = session.scalar(
            select(ClaimEvidence).where(
                ClaimEvidence.revision_id == revision.id,
                ClaimEvidence.source_occurrence_id == occurrence.id,
                ClaimEvidence.source_hash == candidate.evidence.source_hash,
                ClaimEvidence.locator == candidate.evidence.locator,
            )
        )
        if evidence_row is None:
            evidence_row = ClaimEvidence(
                id=str(uuid4()),
                revision_id=revision.id,
                source_document_id=document.id,
                source_occurrence_id=occurrence.id,
                source_key=candidate.evidence.source_key,
                source_hash=candidate.evidence.source_hash,
                locator=candidate.evidence.locator,
                excerpt=candidate.evidence.excerpt,
            )
            session.add(evidence_row)
            session.flush()
        support = session.scalar(
            select(ClaimSupportAssertion).where(
                ClaimSupportAssertion.claim_id == claim.id,
                ClaimSupportAssertion.revision_id == revision.id,
            ).order_by(ClaimSupportAssertion.created_at.desc())
        )
        if support is None or support.support_state != "supported":
            session.add(
                ClaimSupportAssertion(
                    id=str(uuid4()),
                    claim_id=claim.id,
                    revision_id=revision.id,
                    support_state="supported",
                    support_type="documentary",
                    source_evidence_id=evidence_row.id,
                    employer_key=revision.employer_key,
                    period_start=revision.period_start,
                    period_end=revision.period_end,
                    actor="curated_import",
                    reason="Exact documentary evidence imported",
                    supersedes_assertion_id=support.id if support is not None else None,
                )
            )

    def _apply_snapshot(
        self, snapshot: _PreviewSnapshot
    ) -> tuple[str, int, int, tuple[str, ...], tuple[str, ...]]:
        def apply_import(
            session: Session,
        ) -> tuple[str, int, int, tuple[str, ...], tuple[str, ...]]:
            run_id = str(uuid4())
            run = ImportRun(
                id=run_id,
                manifest_version=MANIFEST_VERSION,
                candidate_digest=snapshot.preview.candidate_digest,
                status="incomplete" if snapshot.preview.incomplete else "committed",
                complete=not snapshot.preview.incomplete,
            )
            session.add(run)
            for status in snapshot.preview.source_statuses:
                session.add(
                    ImportRunSource(
                        id=str(uuid4()),
                        import_run_id=run_id,
                        source_key=status.source_key,
                        status=status.status,
                        content_hash=status.content_hash,
                        failure_class=None if status.status == "ready" else status.status,
                        redacted_message=status.message or None,
                    )
                )
            created_claims = 0
            created_revisions = 0
            changed: set[str] = set()
            current_claim_ids: set[str] = set()
            for candidate in snapshot.candidates:
                document = self._find_or_create_document(session, candidate)
                occurrence = self._find_or_create_occurrence(session, candidate)
                claim, revision, new_claim, new_revision = self._upsert_candidate(
                    session, candidate
                )
                self._attach_evidence_and_support(
                    session, candidate, claim, revision, document, occurrence
                )
                created_claims += int(new_claim)
                created_revisions += int(new_revision)
                if not new_claim and new_revision:
                    changed.add(claim.canonical_key)
                current_claim_ids.add(claim.id)
                existing_link = session.scalar(
                    select(ImportRunOccurrence.id).where(
                        ImportRunOccurrence.import_run_id == run_id,
                        ImportRunOccurrence.source_occurrence_id == occurrence.id,
                    )
                )
                if existing_link is None:
                    session.add(
                        ImportRunOccurrence(
                            id=str(uuid4()),
                            import_run_id=run_id,
                            source_occurrence_id=occurrence.id,
                            claim_id=claim.id,
                            revision_id=revision.id,
                        )
                    )
            stale: list[str] = []
            for claim in session.scalars(select(Claim)).all():
                should_be_stale = claim.id not in current_claim_ids
                if run.complete and should_be_stale and not claim.stale:
                    claim.stale = True
                    claim.version += 1
                    stale.append(claim.canonical_key)
                    if claim.active_revision_id is not None:
                        active_revision = session.get(ClaimRevision, claim.active_revision_id)
                        prior_support = session.scalar(
                            select(ClaimSupportAssertion)
                            .where(
                                ClaimSupportAssertion.claim_id == claim.id,
                                ClaimSupportAssertion.revision_id == claim.active_revision_id,
                            )
                            .order_by(ClaimSupportAssertion.created_at.desc())
                        )
                        if active_revision is not None:
                            session.add(
                                ClaimSupportAssertion(
                                    id=str(uuid4()),
                                    claim_id=claim.id,
                                    revision_id=active_revision.id,
                                    support_state="unsupported",
                                    support_type="loss",
                                    source_evidence_id=None,
                                    employer_key=active_revision.employer_key,
                                    period_start=active_revision.period_start,
                                    period_end=active_revision.period_end,
                                    actor="curated_import",
                                    reason="No occurrence supports this revision in the latest run",
                                    supersedes_assertion_id=(
                                        prior_support.id if prior_support is not None else None
                                    ),
                                )
                            )
            from job_search_cockpit.facts.conflicts import rebuild_conflicts

            rebuild_conflicts(session, run_id, close_obsolete=run.complete)
            return run_id, created_claims, created_revisions, tuple(sorted(changed)), tuple(stale)

        return self.coordinator.run(apply_import, "curated_import", expected_version=None)

    def _record_attempt(
        self,
        snapshot: _PreviewSnapshot,
        session_id: str,
        outcome: str,
        failure: Exception | None,
    ) -> str:
        attempt_id = str(uuid4())
        statuses = {
            status.source_key: {"status": status.status, "content_hash": status.content_hash}
            for status in snapshot.preview.source_statuses
        }

        def record(session: Session) -> str:
            session.add(
                ImportAttempt(
                    id=attempt_id,
                    preview_id=snapshot.preview.id,
                    candidate_digest=snapshot.preview.candidate_digest,
                    manifest_version=MANIFEST_VERSION,
                    outcome=outcome,
                    source_statuses_json=statuses,
                    failure_class=type(failure).__name__ if failure else None,
                    redacted_message=self._redacted_failure(failure),
                    session_fingerprint=sha256(session_id.encode()).hexdigest(),
                    created_at=datetime.now(UTC),
                )
            )
            return attempt_id

        try:
            return self.coordinator.run(record, "record_import_attempt", expected_version=None)
        except Exception:
            self.coordinator.recovery_ledger.append(
                RecoveryEvent(
                    event_id=attempt_id,
                    event_type="import_attempt",
                    payload={
                        "preview_id": snapshot.preview.id,
                        "candidate_digest": snapshot.preview.candidate_digest,
                        "manifest_version": MANIFEST_VERSION,
                        "outcome": outcome,
                        "source_statuses": statuses,
                        "failure_class": type(failure).__name__ if failure else "",
                        "redacted_message": self._redacted_failure(failure) or "",
                        "session_fingerprint": sha256(session_id.encode()).hexdigest(),
                    },
                    created_at=datetime.now(UTC),
                )
            )
            return attempt_id

    def _redacted_failure(self, failure: Exception | None) -> str | None:
        if failure is None:
            return None
        if isinstance(failure, PreviewRejected):
            return "Import preview rejected by safety checks."
        return "Import failed safely; no claims were committed."

    def _record_unavailable_attempt(
        self,
        preview_id: str,
        session_id: str,
        failure: PreviewRejected,
    ) -> str:
        attempt_id = str(uuid4())
        statuses = {
            source.key: {"status": "unavailable", "content_hash": None}
            for source in self.settings.sources
        }

        def record(session: Session) -> str:
            session.add(
                ImportAttempt(
                    id=attempt_id,
                    preview_id=preview_id,
                    candidate_digest="0" * 64,
                    manifest_version=MANIFEST_VERSION,
                    outcome="rejected",
                    source_statuses_json=statuses,
                    failure_class=type(failure).__name__,
                    redacted_message=self._redacted_failure(failure),
                    session_fingerprint=sha256(session_id.encode()).hexdigest(),
                    created_at=datetime.now(UTC),
                )
            )
            return attempt_id

        try:
            return self.coordinator.run(record, "record_import_attempt", expected_version=None)
        except Exception:
            self.coordinator.recovery_ledger.append(
                RecoveryEvent(
                    event_id=attempt_id,
                    event_type="import_attempt",
                    payload={
                        "preview_id": preview_id,
                        "candidate_digest": "0" * 64,
                        "manifest_version": MANIFEST_VERSION,
                        "outcome": "rejected",
                        "source_statuses": statuses,
                        "failure_class": type(failure).__name__,
                        "redacted_message": self._redacted_failure(failure) or "",
                        "session_fingerprint": sha256(session_id.encode()).hexdigest(),
                    },
                    created_at=datetime.now(UTC),
                )
            )
            return attempt_id

    def apply(
        self,
        preview_id: str,
        session_id: str,
        now: datetime,
        *,
        confirm_incomplete: bool = False,
    ) -> AppliedImport:
        del now
        try:
            snapshot = self._consume_preview(preview_id, session_id)
        except PreviewRejected as error:
            with self._preview_lock:
                known_snapshot = self._previews.get(preview_id)
            if known_snapshot is None:
                self._record_unavailable_attempt(preview_id, session_id, error)
            else:
                self._record_attempt(known_snapshot, session_id, "rejected", error)
            raise
        if snapshot.preview.incomplete and not confirm_incomplete:
            incomplete_error = PreviewRejected(
                "An incomplete import requires explicit confirmation."
            )
            self._record_attempt(snapshot, session_id, "rejected", incomplete_error)
            raise incomplete_error
        try:
            self._revalidate_sources(snapshot)
            run_id, created_claims, created_revisions, changed, stale = self._apply_snapshot(
                snapshot
            )
        except Exception as error:
            outcome = "rejected" if isinstance(error, PreviewRejected) else "failed"
            self._record_attempt(snapshot, session_id, outcome, error)
            raise
        attempt_id = self._record_attempt(snapshot, session_id, "committed", None)
        return AppliedImport(
            run_id,
            attempt_id,
            created_claims,
            created_revisions,
            changed,
            stale,
            snapshot.preview.source_statuses,
        )
