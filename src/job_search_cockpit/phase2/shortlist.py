from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ShortlistCandidate:
    assessment_id: str
    score: int
    hard_gates_pass: bool = True
    official_source_current: bool = True
    assessment_current: bool = True
    qualified_band: str = "worthwhile"

    def __post_init__(self) -> None:
        if not self.assessment_id.strip():
            raise ValueError("assessment ID is required")
        if not 0 <= self.score <= 100:
            raise ValueError("score must be between zero and 100")
        if self.qualified_band not in {"strong", "worthwhile", "worthwhile_with_required_gap"}:
            raise ValueError("qualified band is not eligible for the focused shortlist")


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
    ordered = sorted(eligible, key=lambda candidate: (-candidate.score, candidate.assessment_id))
    return tuple(ordered[:limit])
