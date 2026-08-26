from dataclasses import dataclass
from enum import StrEnum


class GateResult(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


class RequirementKind(StrEnum):
    REQUIRED = "required"
    MATERIAL_RESPONSIBILITY = "material_responsibility"
    PREFERRED = "preferred"


class EvidenceRelation(StrEnum):
    DIRECT = "direct"
    ADJACENT = "adjacent"
    NONE = "none"


class ConfidenceState(StrEnum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class MatchScoreComponents:
    """The fixed seven-component Phase II match-score breakdown."""

    role: int
    domain: int
    responsibility: int
    technical: int
    outcome: int
    seniority: int
    evidence: int

    def __post_init__(self) -> None:
        maxima = {
            "role": 25,
            "domain": 20,
            "responsibility": 15,
            "technical": 15,
            "outcome": 10,
            "seniority": 10,
            "evidence": 5,
        }
        for name, maximum in maxima.items():
            value = getattr(self, name)
            if not 0 <= value <= maximum:
                raise ValueError(f"{name} score exceeds its approved maximum")

    @property
    def total(self) -> int:
        return sum(
            (
                self.role,
                self.domain,
                self.responsibility,
                self.technical,
                self.outcome,
                self.seniority,
                self.evidence,
            )
        )
