from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ShortlistCandidate:
    assessment_id: str
    score: int

    def __post_init__(self) -> None:
        if not self.assessment_id.strip():
            raise ValueError("assessment ID is required")
        if not 0 <= self.score <= 100:
            raise ValueError("score must be between zero and 100")


def focused_shortlist(
    candidates: tuple[ShortlistCandidate, ...], *, limit: int = 20
) -> tuple[ShortlistCandidate, ...]:
    if not 1 <= limit <= 20:
        raise ValueError("focused shortlist limit must be between one and 20")
    ordered = sorted(candidates, key=lambda candidate: (-candidate.score, candidate.assessment_id))
    return tuple(ordered[:limit])
