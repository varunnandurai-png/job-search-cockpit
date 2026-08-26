from dataclasses import dataclass

from job_search_cockpit.phase1_contract.snapshots import Phase1ResumeFactProjectionRequest
from job_search_cockpit.phase2.assessment_types import (
    ComponentAnchor,
    ConfidenceState,
    EvidenceRelation,
    RequirementKind,
)
from job_search_cockpit.phase2.requirements import build_requirement_ledger
from job_search_cockpit.ports import Phase1MatchingPort


class AssessmentUnavailable(ValueError):
    """Raised when an assessment cannot use current approved Phase I evidence."""


class AssessmentEvidenceService:
    def __init__(self, phase1_port: Phase1MatchingPort) -> None:
        self._phase1_port = phase1_port

    def require_complete_evidence(self, requirement_ids: tuple[str, ...]) -> None:
        projection = self._phase1_port.resume_fact_projection(
            Phase1ResumeFactProjectionRequest(requirement_ids=requirement_ids)
        )
        if self._phase1_port.revalidate_resume_fact_projection(projection) != projection:
            raise AssessmentUnavailable("Phase I evidence changed during assessment.")
        if not build_requirement_ledger(projection).drafting_allowed:
            raise AssessmentUnavailable("Assessment lacks approved evidence.")


_LOW_CONFIDENCE_REASONS = frozenset(
    {
        "unofficial_or_stale_source",
        "coverage_ledger_incomplete",
        "fact_set_incomplete",
        "gate_clause_uncertain",
        "required_clause_uncertain",
        "material_responsibility_uncertain",
        "mapping_predicate_unvalidated",
        "parse_or_schema_failure",
        "assessment_instability",
        "current_generation_unavailable",
    }
)
_MEDIUM_CONFIDENCE_REASONS = frozenset(
    {
        "preferred_clause_uncertain",
        "preferred_mapping_none_due_ambiguity",
        "preferred_taxonomy_adjudication_pending",
    }
)


def resolve_confidence(reason_codes: tuple[str, ...]) -> ConfidenceState:
    reasons = set(reason_codes)
    if not reasons:
        return ConfidenceState.HIGH
    if reasons & _LOW_CONFIDENCE_REASONS or not reasons <= _MEDIUM_CONFIDENCE_REASONS:
        return ConfidenceState.LOW
    return ConfidenceState.MEDIUM


@dataclass(frozen=True, slots=True)
class ComponentContribution:
    requirement_id: str
    points: int
    relation: EvidenceRelation

    def __post_init__(self) -> None:
        if not self.requirement_id.strip():
            raise ValueError("requirement ID is required")
        if self.points < 0:
            raise ValueError("contribution points must be non-negative")


@dataclass(frozen=True, slots=True)
class ComponentRequirement:
    requirement_id: str
    kind: RequirementKind
    relation: EvidenceRelation


def component_anchor(requirements: tuple[ComponentRequirement, ...]) -> ComponentAnchor:
    if not requirements:
        return ComponentAnchor.NONE
    weights = {
        RequirementKind.REQUIRED: 3,
        RequirementKind.MATERIAL_RESPONSIBILITY: 2,
        RequirementKind.PREFERRED: 1,
    }
    total = sum(weights[requirement.kind] for requirement in requirements)
    contribution = sum(
        weights[requirement.kind]
        for requirement in requirements
        if requirement.relation is EvidenceRelation.DIRECT
    ) + sum(
        weights[requirement.kind]
        for requirement in requirements
        if requirement.relation is EvidenceRelation.ADJACENT
    ) / 2
    coverage = contribution / total
    if coverage == 0:
        return ComponentAnchor.NONE
    if coverage < 0.35:
        return ComponentAnchor.ADJACENT
    if coverage < 0.65:
        return ComponentAnchor.PARTIAL
    if coverage < 0.85:
        return ComponentAnchor.STRONG
    direct_count = sum(
        requirement.relation is EvidenceRelation.DIRECT for requirement in requirements
    )
    if direct_count >= 2 and not any(
        requirement.kind is RequirementKind.REQUIRED
        and requirement.relation is EvidenceRelation.NONE
        for requirement in requirements
    ):
        return ComponentAnchor.CLOSE
    return ComponentAnchor.STRONG


def anchor_points(maximum: int, anchor: ComponentAnchor) -> int:
    anchors = {
        20: (0, 5, 10, 15, 20),
        15: (0, 4, 8, 12, 15),
        10: (0, 3, 5, 8, 10),
        5: (0, 1, 3, 4, 5),
    }
    try:
        values = anchors[maximum]
    except KeyError as error:
        raise ValueError("component maximum has no approved anchors") from error
    return values[
        {
            ComponentAnchor.NONE: 0,
            ComponentAnchor.ADJACENT: 1,
            ComponentAnchor.PARTIAL: 2,
            ComponentAnchor.STRONG: 3,
            ComponentAnchor.CLOSE: 4,
        }[anchor]
    ]


def calculate_component_score(
    maximum: int, contributions: tuple[ComponentContribution, ...]
) -> int:
    """Return a capped score using at most one cited mapping per requirement."""
    if maximum < 0:
        raise ValueError("component maximum must be non-negative")
    winning_points: dict[str, int] = {}
    for contribution in contributions:
        if contribution.relation is EvidenceRelation.NONE:
            continue
        winning_points[contribution.requirement_id] = max(
            winning_points.get(contribution.requirement_id, 0), contribution.points
        )
    return min(maximum, sum(winning_points.values()))
