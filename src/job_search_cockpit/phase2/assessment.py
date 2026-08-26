from dataclasses import dataclass

from job_search_cockpit.phase1_contract.snapshots import Phase1ResumeFactProjectionRequest
from job_search_cockpit.phase2.assessment_types import EvidenceRelation
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
