import re
from dataclasses import dataclass
from enum import StrEnum


class GateResult(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


class EligibilityState(StrEnum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    NEEDS_CLARIFICATION = "needs_clarification"


class RequirementKind(StrEnum):
    REQUIRED = "required"
    MATERIAL_RESPONSIBILITY = "material_responsibility"
    PREFERRED = "preferred"


class EvidenceRelation(StrEnum):
    DIRECT = "direct"
    ADJACENT = "adjacent"
    NONE = "none"


_MAPPING_REASON_CODES = {
    EvidenceRelation.DIRECT: frozenset(
        {
            "direct/exact_capability_performed",
            "direct/exact_domain_experience",
            "direct/exact_technical_object_used",
            "direct/numeric_minimum_met",
            "direct/outcome_or_scale_met",
        }
    ),
    EvidenceRelation.ADJACENT: frozenset(
        {
            "adjacent/same_capability_lower_ownership",
            "adjacent/approved_taxonomy_neighbor",
            "adjacent/numeric_near_minimum",
            "adjacent/scale_near_minimum",
        }
    ),
    EvidenceRelation.NONE: frozenset(
        {
            "none/no_approved_evidence_found",
            "none/incomparable_or_ambiguous",
        }
    ),
}

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
class LocationEligibilityPath:
    """A single target-location result that cannot borrow another path's evidence."""

    location_id: str
    result: GateResult
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.location_id.strip():
            raise ValueError("location ID is required")
        if any(
            re.fullmatch(r"[a-z][a-z0-9_/-]{0,119}", reason_code) is None
            for reason_code in self.reason_codes
        ):
            raise ValueError("location reason codes must be bounded")


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
        if self.reason_code not in _MAPPING_REASON_CODES[self.relation]:
            raise ValueError("mapping reason code is not approved for its evidence relation")
        identifiers = (self.claim_id, self.revision_id, self.support_assertion_id)
        if self.relation is EvidenceRelation.NONE:
            if any(identifier is not None for identifier in identifiers):
                raise ValueError("no-support mapping cannot include a Phase I fact identifier")
            return
        if not all(identifier is not None and identifier.strip() for identifier in identifiers):
            raise ValueError("claimed support requires exact Phase I fact identifiers")


def resolve_qualified_match_band(
    *,
    raw_score: int,
    meaningful_role_and_responsibility: bool,
    worthwhile_structure: bool,
    unsupported_required: bool,
    all_critical_floors_pass: bool,
) -> QualifiedMatchBand:
    if raw_score < 55 or not meaningful_role_and_responsibility:
        return QualifiedMatchBand.WEAK
    if raw_score < 70 or not worthwhile_structure:
        return QualifiedMatchBand.EXPLORATORY
    if unsupported_required:
        return QualifiedMatchBand.WORTHWHILE_WITH_REQUIRED_GAP
    if raw_score >= 85 and all_critical_floors_pass:
        return QualifiedMatchBand.STRONG
    return QualifiedMatchBand.WORTHWHILE


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
    critical_floors_pass: bool
    meaningful_role_and_responsibility: bool
    worthwhile_structure: bool
    unsupported_required: bool

    def __post_init__(self) -> None:
        if not all(
            1 <= len(identifier.strip()) <= 36
            for identifier in (self.assessment_id, self.job_revision_id)
        ):
            raise ValueError("assessment and job revision IDs must fit persisted metadata")
        minimum_score = {
            QualifiedMatchBand.STRONG: 85,
            QualifiedMatchBand.WORTHWHILE: 70,
            QualifiedMatchBand.WORTHWHILE_WITH_REQUIRED_GAP: 70,
        }.get(self.qualified_band)
        if minimum_score is not None and self.total_score < minimum_score:
            raise ValueError(
                f"{self.qualified_band.value.replace('_', ' ')} band requires a raw score "
                f"of at least {minimum_score}"
            )
        if self.qualified_band is QualifiedMatchBand.STRONG and not self.critical_floors_pass:
            raise ValueError("strong band requires all critical component floors")
        if self.qualified_band is not resolve_qualified_match_band(
            raw_score=self.total_score,
            meaningful_role_and_responsibility=self.meaningful_role_and_responsibility,
            worthwhile_structure=self.worthwhile_structure,
            unsupported_required=self.unsupported_required,
            all_critical_floors_pass=self.critical_floors_pass,
        ):
            raise ValueError("qualified band does not match its score inputs")

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
