from datetime import UTC, datetime, timedelta

from job_search_cockpit.phase2.application_drafts import (
    ReusableAnswer,
    answer_reusable_for,
    question_label_fingerprint,
)


def test_reusable_answer_requires_the_same_normalized_question_label() -> None:
    created_at = datetime(2026, 8, 24, tzinfo=UTC)
    answer = ReusableAnswer(
        id="sanitized-answer-1",
        question_label_fingerprint=question_label_fingerprint("Work authorization"),
        phase1_revision_id="sanitized-revision-1",
        projection_fingerprint="a" * 64,
        created_at=created_at,
        expires_at=created_at + timedelta(days=45),
    )

    assert answer_reusable_for(answer, "  Work   authorization  ", created_at) is True
    assert answer_reusable_for(answer, "Authorization to work", created_at) is False


def test_reusable_answer_expires_after_forty_five_days() -> None:
    created_at = datetime(2026, 8, 24, tzinfo=UTC)
    answer = ReusableAnswer(
        id="sanitized-answer-1",
        question_label_fingerprint=question_label_fingerprint("Work authorization"),
        phase1_revision_id="sanitized-revision-1",
        projection_fingerprint="a" * 64,
        created_at=created_at,
        expires_at=created_at + timedelta(days=45),
    )

    assert answer_reusable_for(answer, "Work authorization", answer.expires_at) is False
