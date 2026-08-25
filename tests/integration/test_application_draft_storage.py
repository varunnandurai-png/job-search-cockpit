from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest

from job_search_cockpit.phase1_contract.snapshots import (
    Phase1ResumeFactProjection,
    Phase1ResumeFactSnapshot,
)
from job_search_cockpit.phase2.application_drafts import (
    ApplicationDraftService,
    ApplicationDraftStore,
    DraftAnswerSelection,
    ReusableAnswerService,
    ReusableAnswerStore,
)
from job_search_cockpit.phase2.config import Phase2Settings
from job_search_cockpit.phase2.database import create_phase2_engine, upgrade_phase2_database
from job_search_cockpit.phase2.mutation import Phase2InstanceLock, Phase2MutationCoordinator
from job_search_cockpit.phase2.resume_safety import (
    ResumePreparationAttempt,
    ResumePreparationAttemptStore,
    ResumePreparationError,
    VerifiedJobPreparationAuthorization,
)


@contextmanager
def _coordinator(settings: Phase2Settings) -> Iterator[Phase2MutationCoordinator]:
    upgrade_phase2_database(f"sqlite:///{settings.database_path}")
    engine = create_phase2_engine(settings)
    lock = Phase2InstanceLock.acquire(settings)
    coordinator = Phase2MutationCoordinator(settings, engine, lock)
    try:
        yield coordinator
    finally:
        coordinator.dispose()
        lock.release()


def _authorization() -> VerifiedJobPreparationAuthorization:
    return VerifiedJobPreparationAuthorization(
        job_id="sanitized-job-1",
        job_revision_id="sanitized-job-revision-1",
        selected_location_path_fingerprint="a" * 64,
        authorization_id="sanitized-authorization-1",
        authorization_nonce="sanitized-nonce-1",
        eligibility="eligible",
        expires_at=datetime(2026, 8, 24, 9, 15, tzinfo=UTC),
        phase1_profile_fingerprint="b" * 64,
        phase1_profile_generation=1,
        phase1_readiness_fingerprint="c" * 64,
        phase1_readiness_generation=1,
        phase1_authority_fingerprint="d" * 64,
        phase1_authority_generation=1,
        phase1_restore_generation=1,
        phase2_activation_generation=1,
        phase2_restore_generation=1,
    )


def _record_attempt(
    coordinator: Phase2MutationCoordinator,
) -> ResumePreparationAttempt:
    return ResumePreparationAttemptStore(coordinator).record(_authorization())


def _projection(revision_id: str) -> Phase1ResumeFactProjection:
    return Phase1ResumeFactProjection(
        requirement_ids=("application.answer.work_authorization",),
        facts=(
            Phase1ResumeFactSnapshot(
                requirement_id="application.answer.work_authorization",
                claim_id="sanitized-claim-1",
                revision_id=revision_id,
                support_assertion_id="sanitized-support-1",
                safe_wording="Eligible to work.",
                employer_key=None,
                period_start=None,
                period_end=None,
            ),
        ),
        profile_fingerprint="a" * 64,
        profile_generation=1,
        readiness_fingerprint="b" * 64,
        readiness_generation=1,
        authority_fingerprint="c" * 64,
        authority_generation=1,
        restore_generation=0,
        fingerprint="d" * 64,
    )


class CurrentProjectionPort:
    def revalidate_resume_fact_projection(
        self, expected: Phase1ResumeFactProjection
    ) -> Phase1ResumeFactProjection:
        return expected


def test_superseding_an_answer_flags_existing_no_submit_drafts(
    phase2_settings: Phase2Settings,
) -> None:
    created_at = datetime(2026, 8, 24, 9, 0, tzinfo=UTC)
    with _coordinator(phase2_settings) as coordinator:
        answers = ReusableAnswerService(
            CurrentProjectionPort(),
            ReusableAnswerStore(coordinator),
            now=lambda: created_at,
        )
        drafts = ApplicationDraftStore(coordinator)
        attempt = _record_attempt(coordinator)
        original = answers.record_approved(
            question_label="Work authorization",
            projection=_projection("sanitized-revision-1"),
            phase1_revision_id="sanitized-revision-1",
        )
        draft = drafts.create(
            resume_preparation_attempt_id=attempt.id,
            job_id=attempt.job_id,
            job_revision_id=attempt.job_revision_id,
            final_resume_version_id=None,
            approved_answers=(
                DraftAnswerSelection(original.id, "Work authorization"),
            ),
            created_at=created_at,
        )

        replacement = answers.record_approved(
            question_label="Work authorization",
            projection=_projection("sanitized-revision-2"),
            phase1_revision_id="sanitized-revision-2",
            supersedes_answer_id=original.id,
        )

        assert replacement.supersedes_answer_id == original.id
        assert draft.state == "manual_review_required_no_submission"
        assert drafts.review_flags_for(draft.id) == ((original.id, replacement.id),)


def test_application_draft_references_only_existing_approved_answer_ids(
    phase2_settings: Phase2Settings,
) -> None:
    with _coordinator(phase2_settings) as coordinator:
        drafts = ApplicationDraftStore(coordinator)
        attempt = _record_attempt(coordinator)

        with pytest.raises(ValueError, match="approved reusable answer"):
            drafts.create(
                resume_preparation_attempt_id=attempt.id,
                job_id=attempt.job_id,
                job_revision_id=attempt.job_revision_id,
                final_resume_version_id=None,
                approved_answers=(DraftAnswerSelection("missing-answer", "Work authorization"),),
                created_at=datetime(2026, 8, 24, 9, 0, tzinfo=UTC),
            )


def test_application_draft_rejects_a_dangling_preparation_attempt(
    phase2_settings: Phase2Settings,
) -> None:
    with _coordinator(phase2_settings) as coordinator:
        drafts = ApplicationDraftStore(coordinator)

        with pytest.raises(ValueError, match="preparation attempt"):
            drafts.create(
                resume_preparation_attempt_id="missing-attempt",
                job_id="sanitized-job-1",
                job_revision_id="sanitized-job-revision-1",
                final_resume_version_id=None,
                approved_answers=(),
                created_at=datetime(2026, 8, 24, 9, 0, tzinfo=UTC),
            )


def test_application_draft_rejects_an_answer_for_a_different_question_label(
    phase2_settings: Phase2Settings,
) -> None:
    created_at = datetime(2026, 8, 24, 9, 0, tzinfo=UTC)
    with _coordinator(phase2_settings) as coordinator:
        answers = ReusableAnswerService(
            CurrentProjectionPort(),
            ReusableAnswerStore(coordinator),
            now=lambda: created_at,
        )
        drafts = ApplicationDraftStore(coordinator)
        attempt = _record_attempt(coordinator)
        answer = answers.record_approved(
            question_label="Work authorization",
            projection=_projection("sanitized-revision-1"),
            phase1_revision_id="sanitized-revision-1",
        )

        with pytest.raises(ValueError, match="exact question label"):
            drafts.create(
                resume_preparation_attempt_id=attempt.id,
                job_id=attempt.job_id,
                job_revision_id=attempt.job_revision_id,
                final_resume_version_id=None,
                approved_answers=(
                    DraftAnswerSelection(answer.id, "Authorization to work"),
                ),
                created_at=created_at,
            )


def test_reusable_answer_service_requires_a_current_phase1_projection(
    phase2_settings: Phase2Settings,
) -> None:
    projection = _projection("sanitized-revision-1")

    with _coordinator(phase2_settings) as coordinator:
        service = ReusableAnswerService(
            CurrentProjectionPort(),
            ReusableAnswerStore(coordinator),
            now=lambda: datetime(2026, 8, 24, 9, 0, tzinfo=UTC),
        )

        answer = service.record_approved(
            question_label="Work authorization",
            projection=projection,
            phase1_revision_id="sanitized-revision-1",
        )

    assert answer.phase1_revision_id == "sanitized-revision-1"
    assert answer.projection_fingerprint == "d" * 64


def test_application_draft_service_rejects_an_attempt_for_a_different_job(
    phase2_settings: Phase2Settings,
) -> None:
    authorization = VerifiedJobPreparationAuthorization(
        job_id="sanitized-job-1",
        job_revision_id="sanitized-job-revision-1",
        selected_location_path_fingerprint="a" * 64,
        authorization_id="sanitized-authorization-1",
        authorization_nonce="sanitized-nonce-1",
        eligibility="eligible",
        expires_at=datetime(2026, 8, 24, 9, 15, tzinfo=UTC),
        phase1_profile_fingerprint="b" * 64,
        phase1_profile_generation=1,
        phase1_readiness_fingerprint="c" * 64,
        phase1_readiness_generation=1,
        phase1_authority_fingerprint="d" * 64,
        phase1_authority_generation=1,
        phase1_restore_generation=1,
        phase2_activation_generation=1,
        phase2_restore_generation=1,
    )
    attempt = ResumePreparationAttempt(
        id="sanitized-attempt-1",
        job_id="different-job",
        job_revision_id=authorization.job_revision_id,
        authorization_id=authorization.authorization_id,
        phase2_activation_generation=authorization.phase2_activation_generation,
        authorization=authorization,
    )

    class StableAuthorizationPort:
        def revalidate_resume_authorization(
            self, expected: VerifiedJobPreparationAuthorization
        ) -> VerifiedJobPreparationAuthorization:
            return expected

    with _coordinator(phase2_settings) as coordinator:
        service = ApplicationDraftService(
            StableAuthorizationPort(),
            ApplicationDraftStore(coordinator),
            now=lambda: datetime(2026, 8, 24, 9, 0, tzinfo=UTC),
        )

        with pytest.raises(ResumePreparationError, match="does not match"):
            service.create_no_submit_draft(
                attempt=attempt,
                final_resume_version_id=None,
                approved_answers=(),
            )
