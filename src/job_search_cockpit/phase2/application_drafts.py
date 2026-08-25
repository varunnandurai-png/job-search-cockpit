from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from re import fullmatch
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from job_search_cockpit.phase1_contract.snapshots import Phase1ResumeFactProjection
from job_search_cockpit.phase2.models import (
    Phase2ApplicationDraft,
    Phase2ApplicationDraftAnswer,
    Phase2ApplicationDraftReviewFlag,
    Phase2ResumePreparationAttempt,
    Phase2ReusableAnswer,
)
from job_search_cockpit.phase2.mutation import Phase2MutationCoordinator
from job_search_cockpit.phase2.resume_safety import (
    ResumePreparationAttempt,
    ResumePreparationError,
    VerifiedJobPreparationPort,
)
from job_search_cockpit.ports import Phase1MatchingPort

_REUSE_WINDOW = timedelta(days=45)
_NO_SUBMISSION_STATE = "manual_review_required_no_submission"


def question_label_fingerprint(label: str) -> str:
    normalized = " ".join(label.split()).casefold()
    if not normalized or len(normalized) > 300:
        raise ValueError("A clearly labelled question is required.")
    return sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ReusableAnswer:
    id: str
    question_label_fingerprint: str
    phase1_revision_id: str
    projection_fingerprint: str
    created_at: datetime
    expires_at: datetime
    supersedes_answer_id: str | None = None


@dataclass(frozen=True, slots=True)
class ApprovedAnswerReference:
    phase1_revision_id: str
    projection_fingerprint: str
    projection_revision_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ApplicationDraft:
    id: str
    resume_preparation_attempt_id: str
    job_id: str
    job_revision_id: str
    final_resume_version_id: str | None
    approved_answer_ids: tuple[str, ...]
    state: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class DraftAnswerSelection:
    reusable_answer_id: str
    question_label: str


def answer_reusable_for(answer: ReusableAnswer, label: str, now: datetime) -> bool:
    return (
        now < answer.expires_at
        and answer.question_label_fingerprint == question_label_fingerprint(label)
    )


def approved_answer_reference(
    projection: Phase1ResumeFactProjection, phase1_revision_id: str
) -> ApprovedAnswerReference:
    return ApprovedAnswerReference(
        phase1_revision_id=phase1_revision_id,
        projection_fingerprint=projection.fingerprint,
        projection_revision_ids=tuple(fact.revision_id for fact in projection.facts),
    )


def validate_approved_answer_reference(reference: ApprovedAnswerReference) -> bool:
    return (
        bool(reference.phase1_revision_id.strip())
        and fullmatch(r"[0-9a-f]{64}", reference.projection_fingerprint) is not None
        and reference.phase1_revision_id in reference.projection_revision_ids
    )


class ReusableAnswerStore:
    def __init__(self, coordinator: Phase2MutationCoordinator) -> None:
        self._coordinator = coordinator

    def _record(
        self,
        *,
        question_label: str,
        reference: ApprovedAnswerReference,
        created_at: datetime,
        supersedes_answer_id: str | None = None,
    ) -> ReusableAnswer:
        fingerprint = question_label_fingerprint(question_label)
        if not validate_approved_answer_reference(reference):
            raise ValueError("An approved Phase I answer reference is required.")

        def insert(session: Session) -> ReusableAnswer:
            if supersedes_answer_id is not None:
                superseded = session.get(Phase2ReusableAnswer, supersedes_answer_id)
                if superseded is None:
                    raise ValueError("The reusable answer to supersede does not exist.")
                if superseded.question_label_fingerprint != fingerprint:
                    raise ValueError("A changed answer must keep the exact question label.")
            answer = Phase2ReusableAnswer(
                id=str(uuid4()),
                question_label_fingerprint=fingerprint,
                phase1_revision_id=reference.phase1_revision_id,
                projection_fingerprint=reference.projection_fingerprint,
                supersedes_answer_id=supersedes_answer_id,
                created_at=created_at,
                expires_at=created_at + _REUSE_WINDOW,
            )
            session.add(answer)
            session.flush()
            if supersedes_answer_id is not None:
                draft_ids = session.scalars(
                    select(Phase2ApplicationDraftAnswer.application_draft_id).where(
                        Phase2ApplicationDraftAnswer.reusable_answer_id == supersedes_answer_id
                    )
                )
                for draft_id in draft_ids:
                    session.add(
                        Phase2ApplicationDraftReviewFlag(
                            id=str(uuid4()),
                            application_draft_id=draft_id,
                            superseded_answer_id=supersedes_answer_id,
                            replacement_answer_id=answer.id,
                            reason="approved_answer_superseded",
                            created_at=created_at,
                        )
                    )
            return _reusable_answer(answer)

        return self._coordinator.run(insert, "record_reusable_answer")


class ReusableAnswerService:
    def __init__(
        self,
        phase1_port: Phase1MatchingPort,
        store: ReusableAnswerStore,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._phase1_port = phase1_port
        self._store = store
        self._now = now or (lambda: datetime.now(UTC))

    def record_approved(
        self,
        *,
        question_label: str,
        projection: Phase1ResumeFactProjection,
        phase1_revision_id: str,
        supersedes_answer_id: str | None = None,
    ) -> ReusableAnswer:
        if self._phase1_port.revalidate_resume_fact_projection(projection) != projection:
            raise ValueError("The approved Phase I answer projection changed.")
        reference = approved_answer_reference(projection, phase1_revision_id)
        if not validate_approved_answer_reference(reference):
            raise ValueError("The reusable answer is not bound to an approved Phase I projection.")
        return self._store._record(
            question_label=question_label,
            reference=reference,
            created_at=self._now(),
            supersedes_answer_id=supersedes_answer_id,
        )


class ApplicationDraftStore:
    def __init__(self, coordinator: Phase2MutationCoordinator) -> None:
        self._coordinator = coordinator

    def create(
        self,
        *,
        resume_preparation_attempt_id: str,
        job_id: str,
        job_revision_id: str,
        final_resume_version_id: str | None,
        approved_answers: tuple[DraftAnswerSelection, ...],
        created_at: datetime,
    ) -> ApplicationDraft:
        if not all(
            value.strip()
            for value in (resume_preparation_attempt_id, job_id, job_revision_id)
        ):
            raise ValueError("A verified preparation attempt and job revision are required.")
        answer_ids = tuple(answer.reusable_answer_id for answer in approved_answers)
        if len(set(answer_ids)) != len(answer_ids):
            raise ValueError("Approved reusable answers must not be duplicated.")

        def insert(session: Session) -> ApplicationDraft:
            attempt = session.get(Phase2ResumePreparationAttempt, resume_preparation_attempt_id)
            if attempt is None or (attempt.job_id, attempt.job_revision_id) != (
                job_id,
                job_revision_id,
            ):
                raise ValueError("A matching durable preparation attempt is required.")
            stored_answers = {
                answer.id: answer
                for answer in session.scalars(
                    select(Phase2ReusableAnswer).where(Phase2ReusableAnswer.id.in_(answer_ids))
                )
            }
            if len(stored_answers) != len(answer_ids):
                raise ValueError("Every draft answer must be an approved reusable answer.")
            for selection in approved_answers:
                answer = stored_answers[selection.reusable_answer_id]
                if answer.question_label_fingerprint != question_label_fingerprint(
                    selection.question_label
                ):
                    raise ValueError("A reusable answer requires the exact question label.")
                if _as_utc(created_at) >= _as_utc(answer.expires_at):
                    raise ValueError("An expired reusable answer cannot be added to a new draft.")
            draft = Phase2ApplicationDraft(
                id=str(uuid4()),
                resume_preparation_attempt_id=resume_preparation_attempt_id,
                job_id=job_id,
                job_revision_id=job_revision_id,
                final_resume_version_id=final_resume_version_id,
                state=_NO_SUBMISSION_STATE,
                created_at=created_at,
            )
            session.add(draft)
            session.flush()
            for answer_id in answer_ids:
                session.add(
                    Phase2ApplicationDraftAnswer(
                        id=str(uuid4()),
                        application_draft_id=draft.id,
                        reusable_answer_id=answer_id,
                        created_at=created_at,
                    )
                )
            return ApplicationDraft(
                id=draft.id,
                resume_preparation_attempt_id=draft.resume_preparation_attempt_id,
                job_id=draft.job_id,
                job_revision_id=draft.job_revision_id,
                final_resume_version_id=draft.final_resume_version_id,
                approved_answer_ids=answer_ids,
                state=draft.state,
                created_at=draft.created_at,
            )

        return self._coordinator.run(insert, "create_no_submit_application_draft")

    def review_flags_for(self, draft_id: str) -> tuple[tuple[str, str], ...]:
        with self._coordinator._session_factory() as session:
            flags = session.execute(
                select(
                    Phase2ApplicationDraftReviewFlag.superseded_answer_id,
                    Phase2ApplicationDraftReviewFlag.replacement_answer_id,
                )
                .where(Phase2ApplicationDraftReviewFlag.application_draft_id == draft_id)
                .order_by(Phase2ApplicationDraftReviewFlag.created_at)
            )
            return tuple((str(old_id), str(new_id)) for old_id, new_id in flags)


class ApplicationDraftService:
    def __init__(
        self,
        preparation_port: VerifiedJobPreparationPort,
        store: ApplicationDraftStore,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._preparation_port = preparation_port
        self._store = store
        self._now = now or (lambda: datetime.now(UTC))

    def create_no_submit_draft(
        self,
        *,
        attempt: ResumePreparationAttempt,
        final_resume_version_id: str | None,
        approved_answers: tuple[DraftAnswerSelection, ...],
    ) -> ApplicationDraft:
        revalidated = self._preparation_port.revalidate_resume_authorization(
            attempt.authorization
        )
        if revalidated != attempt.authorization:
            raise ResumePreparationError("The verified job authorization changed.")
        if (
            attempt.job_id != revalidated.job_id
            or attempt.job_revision_id != revalidated.job_revision_id
            or attempt.authorization_id != revalidated.authorization_id
            or attempt.phase2_activation_generation != revalidated.phase2_activation_generation
        ):
            raise ResumePreparationError(
                "The preparation attempt does not match its authorization."
            )
        now = self._now()
        if (
            revalidated.expires_at <= now
            or revalidated.eligibility != "eligible"
            or revalidated.unknown_mandatory_rule_codes
        ):
            raise ResumePreparationError("The verified job authorization is no longer usable.")
        return self._store.create(
            resume_preparation_attempt_id=attempt.id,
            job_id=attempt.job_id,
            job_revision_id=attempt.job_revision_id,
            final_resume_version_id=final_resume_version_id,
            approved_answers=approved_answers,
            created_at=now,
        )


def _reusable_answer(answer: Phase2ReusableAnswer) -> ReusableAnswer:
    return ReusableAnswer(
        id=answer.id,
        question_label_fingerprint=answer.question_label_fingerprint,
        phase1_revision_id=answer.phase1_revision_id,
        projection_fingerprint=answer.projection_fingerprint,
        created_at=answer.created_at,
        expires_at=answer.expires_at,
        supersedes_answer_id=answer.supersedes_answer_id,
    )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
