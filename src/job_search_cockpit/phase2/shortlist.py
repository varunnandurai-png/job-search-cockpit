from dataclasses import dataclass, field
from datetime import UTC, datetime

from job_search_cockpit.phase2.assessment_types import ConfidenceState

_CONFIDENCE_ORDER = {
    ConfidenceState.HIGH: 0,
    ConfidenceState.MEDIUM: 1,
    ConfidenceState.LOW: 2,
    ConfidenceState.BLOCKED: 3,
}


@dataclass(frozen=True, slots=True)
class ShortlistCandidate:
    assessment_id: str
    score: int
    hard_gates_pass: bool = True
    official_source_current: bool = True
    assessment_current: bool = True
    qualified_band: str = "worthwhile"
    confidence: ConfidenceState = ConfidenceState.HIGH
    official_verified_at: datetime = field(
        default_factory=lambda: datetime.min.replace(tzinfo=UTC)
    )
    discovered_at: datetime = field(default_factory=lambda: datetime.min.replace(tzinfo=UTC))

    def __post_init__(self) -> None:
        if not self.assessment_id.strip():
            raise ValueError("assessment ID is required")
        if not 0 <= self.score <= 100:
            raise ValueError("score must be between zero and 100")
        if self.qualified_band not in {"strong", "worthwhile", "worthwhile_with_required_gap"}:
            raise ValueError("qualified band is not eligible for the focused shortlist")
        if self.official_verified_at.tzinfo is None or self.discovered_at.tzinfo is None:
            raise ValueError("shortlist timestamps must be timezone-aware")


def focused_shortlist(
    candidates: tuple[ShortlistCandidate, ...], *, limit: int = 20
) -> tuple[ShortlistCandidate, ...]:
    if not 1 <= limit <= 20:
        raise ValueError("focused shortlist limit must be between one and 20")
    eligible = tuple(
        candidate
        for candidate in candidates
        if candidate.hard_gates_pass
        and candidate.official_source_current
        and candidate.assessment_current
        and candidate.score >= 70
    )
    ordered = sorted(
        eligible,
        key=lambda candidate: (
            -candidate.score,
            _CONFIDENCE_ORDER[candidate.confidence],
            -candidate.official_verified_at.timestamp(),
            -candidate.discovered_at.timestamp(),
            candidate.assessment_id,
        ),
    )
    return tuple(ordered[:limit])
