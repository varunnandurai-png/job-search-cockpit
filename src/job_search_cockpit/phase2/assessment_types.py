import re
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
    MEDIUM = "medium"
    LOW = "low"
    BLOCKED = "blocked"


class ComponentAnchor(StrEnum):
    NONE = "none"
    ADJACENT = "adjacent"
    PARTIAL = "partial"
    STRONG = "strong"
    CLOSE = "close"


class QualifiedMatchBand(StrEnum):
    WEAK = "weak"
    EXPLORATORY = "exploratory"
    WORTHWHILE_WITH_REQUIRED_GAP = "worthwhile_with_required_gap"
    STRONG = "strong"
    WORTHWHILE = "worthwhile"


class ScoringComponent(StrEnum):
    ROLE = "role"
    DOMAIN = "domain"
    RESPONSIBILITY = "responsibility"
    OUTCOME = "outcome"
    TECHNICAL = "technical"
    SENIORITY = "seniority"
    EVIDENCE = "evidence"


@dataclass(frozen=True, slots=True)
class Requirement:
    """A bounded, cited requirement reference with no retained listing wording."""

    requirement_id: str
    kind: RequirementKind
    component: ScoringComponent
    source_span_id: str
    start_offset: int
    end_offset: int

    def __post_init__(self) -> None:
        if re.fullmatch(r"[a-z][a-z0-9_.-]{0,254}", self.requirement_id) is None:
            raise ValueError("requirement ID must be canonical")
        if not self.source_span_id.strip():
            raise ValueError("source span ID is required")
        if not 0 <= self.start_offset < self.end_offset <= 200_000:
            raise ValueError("requirement offsets are invalid")


@dataclass(frozen=True, slots=True)
class RequirementEvidenceMapping:
    """One score-relevant relation, bound only to opaque approved fact identifiers."""

    requirement_id: str
    relation: EvidenceRelation
    reason_code: str
    claim_id: str | None = None
    revision_id: str | None = None
    support_assertion_id: str | None = None

    def __post_init__(self) -> None:
        if re.fullmatch(r"[a-z][a-z0-9_.-]{0,254}", self.requirement_id) is None:
            raise ValueError("requirement ID must be canonical")
        if re.fullmatch(r"[a-z][a-z0-9_/-]{0,119}", self.reason_code) is None:
            raise ValueError("mapping reason code must be bounded")
        identifiers = (self.claim_id, self.revision_id, self.support_assertion_id)
        if self.relation is EvidenceRelation.NONE:
            if any(identifier is not None for identifier in identifiers):
                raise ValueError("no-support mapping cannot include a Phase I fact identifier")
            return
        if not all(identifier is not None and identifier.strip() for identifier in identifiers):
            raise ValueError("claimed support requires exact Phase I fact identifiers")


@dataclass(frozen=True, slots=True)
class MatchAssessmentResult:
    """An immutable numeric result whose shortlist eligibility remains fail-closed."""

    assessment_id: str
    job_revision_id: str
    components: "MatchScoreComponents"
    qualified_band: QualifiedMatchBand
    confidence: ConfidenceState
    hard_gates_pass: bool
    current: bool

    def __post_init__(self) -> None:
        if not self.assessment_id.strip() or not self.job_revision_id.strip():
            raise ValueError("assessment and job revision IDs are required")

    @property
    def total_score(self) -> int:
        return self.components.total

    @property
    def focused_shortlist_eligible(self) -> bool:
        return (
            self.hard_gates_pass
            and self.current
            and self.confidence is not ConfidenceState.BLOCKED
            and self.total_score >= 70
            and self.qualified_band
            in {
                QualifiedMatchBand.STRONG,
                QualifiedMatchBand.WORTHWHILE,
                QualifiedMatchBand.WORTHWHILE_WITH_REQUIRED_GAP,
            }
        )


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
            "role": 20,
            "domain": 20,
            "responsibility": 20,
            "technical": 10,
            "outcome": 15,
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
