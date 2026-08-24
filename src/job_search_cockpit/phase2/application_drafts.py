from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256


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


def answer_reusable_for(answer: ReusableAnswer, label: str, now: datetime) -> bool:
    return (
        now < answer.expires_at
        and answer.question_label_fingerprint == question_label_fingerprint(label)
    )
