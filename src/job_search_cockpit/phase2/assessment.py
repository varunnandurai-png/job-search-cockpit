import re
from dataclasses import dataclass
from fractions import Fraction

from job_search_cockpit.phase1_contract.service import Phase1ContractUnavailable
from job_search_cockpit.phase1_contract.snapshots import (
    Phase1ActivationInputs,
    Phase1MatchingFactSetSnapshot,
    Phase1MatchingRequirementQuery,
    Phase1ResumeFactProjectionRequest,
)
from job_search_cockpit.phase2.activation import Phase2ActivationService
from job_search_cockpit.phase2.assessment_types import (
    ComponentAnchor,
    ConfidenceState,
    EvidenceRelation,
    GateResult,
    LocationEligibilityPath,
    MatchAssessmentResult,
    MatchScoreComponents,
    QualifiedMatchBand,
    Requirement,
    RequirementEvidenceMapping,
    RequirementKind,
    ScoringComponent,
    resolve_qualified_match_band,
)
from job_search_cockpit.phase2.requirements import build_requirement_ledger
from job_search_cockpit.phase2.types import (
    Phase2Action,
    Phase2ActivationUnavailable,
    Phase2ActivationView,
)
from job_search_cockpit.ports import Phase1MatchingPort


class AssessmentUnavailable(ValueError):
    """Raised when an assessment cannot use current approved Phase I evidence."""


@dataclass(frozen=True, slots=True)
class AssessmentPublicationCommand:
    """Opaque, locally validated metadata for one append-only match assessment."""

    result: MatchAssessmentResult
    requirements: tuple[Requirement, ...]
    mappings: tuple[RequirementEvidenceMapping, ...]
    gate_result: GateResult
    gate_reason_codes: tuple[str, ...]
    location_paths: tuple[LocationEligibilityPath, ...]
    rubric_version: str
    coverage_ledger_fingerprint: str
    fact_set_fingerprint: str
    assessment_state: str
    shortlist_reason_codes: tuple[str, ...]

    def validate(self) -> None:
        if not self.rubric_version.strip():
            raise ValueError("assessment rubric version is required")
        if self.assessment_state not in {"stable", "adjudicated"}:
            raise ValueError("assessment state is not publishable")
        if any(
            re.fullmatch(r"[a-f0-9]{64}", fingerprint) is None
            for fingerprint in (
                self.coverage_ledger_fingerprint,
                self.fact_set_fingerprint,
            )
        ):
            raise ValueError("assessment fingerprints must be SHA-256 hex digests")
        if any(
            re.fullmatch(r"[a-z][a-z0-9_/-]{0,119}", code) is None
            for code in (*self.gate_reason_codes, *self.shortlist_reason_codes)
        ):
            raise ValueError("assessment reason codes must be bounded")
        requirement_ids = tuple(requirement.requirement_id for requirement in self.requirements)
        if not requirement_ids or len(set(requirement_ids)) != len(requirement_ids):
            raise ValueError("published requirements must be unique")
        mapping_ids = tuple(mapping.requirement_id for mapping in self.mappings)
        if set(mapping_ids) - set(requirement_ids):
            raise ValueError("publication mapping must reference a published requirement")
        if set(mapping_ids) != set(requirement_ids) or len(set(mapping_ids)) != len(mapping_ids):
            raise ValueError("every published requirement needs one evidence mapping")


@dataclass(frozen=True, slots=True)
class AssessmentAuthoritySnapshot:
    """The exact cross-store state that a persisted assessment must bind to."""

    phase1_inputs: Phase1ActivationInputs
    phase2_view: Phase2ActivationView

    def persistence_fields(self) -> dict[str, str | int]:
        return {
            "phase1_profile_fingerprint": self.phase1_inputs.profile.fingerprint,
            "phase1_profile_generation": self.phase1_inputs.profile.active_profile_generation,
            "phase1_readiness_fingerprint": self.phase1_inputs.readiness.fingerprint,
            "phase1_readiness_generation": self.phase1_inputs.readiness.readiness_generation,
            "phase1_authority_fingerprint": self.phase1_inputs.acceptance_receipt.fingerprint,
            "phase1_authority_generation": self.phase1_inputs.readiness.authority_high_water_mark,
            "phase1_restore_generation": self.phase1_inputs.readiness.restore_generation,
            "phase2_activation_generation": self.phase2_view.activation_generation,
            "phase2_restore_generation": self.phase2_view.restore_generation,
        }


class AssessmentAuthorityService:
    """Captures and revalidates the authority fence around local assessment work."""

    def __init__(
        self, phase1_port: Phase1MatchingPort, activation_service: Phase2ActivationService
    ) -> None:
        self._phase1_port = phase1_port
        self._activation_service = activation_service

    def capture_for_assessment(self) -> AssessmentAuthoritySnapshot:
        try:
            phase2_view = self._activation_service.revalidate_before(Phase2Action.SCORING)
            phase1_inputs = self._phase1_port.activation_inputs()
            if self._phase1_port.revalidate_activation_inputs(phase1_inputs) != phase1_inputs:
                raise AssessmentUnavailable("Assessment authority changed during capture.")
        except (Phase1ContractUnavailable, Phase2ActivationUnavailable, ValueError) as error:
            raise AssessmentUnavailable("Assessment authority is unavailable.") from error
        return AssessmentAuthoritySnapshot(phase1_inputs, phase2_view)

    def revalidate_before_publication(
        self, expected: AssessmentAuthoritySnapshot
    ) -> AssessmentAuthoritySnapshot:
        try:
            phase2_view = self._activation_service.revalidate_before(Phase2Action.PUBLICATION)
            phase1_inputs = self._phase1_port.revalidate_activation_inputs(expected.phase1_inputs)
        except (Phase1ContractUnavailable, Phase2ActivationUnavailable, ValueError) as error:
            raise AssessmentUnavailable(
                "Assessment authority changed before publication."
            ) from error
        current = AssessmentAuthoritySnapshot(phase1_inputs, phase2_view)
        if current.persistence_fields() != expected.persistence_fields():
            raise AssessmentUnavailable("Assessment authority changed before publication.")
        return current


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

    def require_complete_matching_facts(
        self, requirement_ids: tuple[str, ...]
    ) -> Phase1MatchingFactSetSnapshot:
        try:
            snapshot = self._phase1_port.matching_fact_set(
                Phase1MatchingRequirementQuery(requirement_ids=requirement_ids)
            )
            current = self._phase1_port.revalidate_matching_fact_set(snapshot)
        except (Phase1ContractUnavailable, ValueError) as error:
            raise AssessmentUnavailable("Assessment matching facts are unavailable.") from error
        if current != snapshot:
            raise AssessmentUnavailable("Assessment matching fact set changed.")
        if snapshot.requirement_ids != requirement_ids or not snapshot.complete:
            raise AssessmentUnavailable("Assessment matching fact set is incomplete.")
        if len({fact.requirement_id for fact in snapshot.facts}) != len(snapshot.facts):
            raise AssessmentUnavailable("Assessment matching fact set is malformed.")
        if any(
            fact.requirement_id not in requirement_ids
            or not all(
                (
                    fact.claim_id.strip(),
                    fact.revision_id.strip(),
                    fact.support_assertion_id.strip(),
                )
            )
            for fact in snapshot.facts
        ):
            raise AssessmentUnavailable("Assessment matching fact set is malformed.")
        return snapshot


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
class QualifiedBandInputs:
    raw_score: int
    meaningful_role_and_responsibility: bool
    worthwhile_structure: bool
    unsupported_required: bool
    all_critical_floors_pass: bool

    def __post_init__(self) -> None:
        if not 0 <= self.raw_score <= 100:
            raise ValueError("raw score must be between zero and 100")


def qualified_match_band(inputs: QualifiedBandInputs) -> QualifiedMatchBand:
    return resolve_qualified_match_band(
        raw_score=inputs.raw_score,
        meaningful_role_and_responsibility=inputs.meaningful_role_and_responsibility,
        worthwhile_structure=inputs.worthwhile_structure,
        unsupported_required=inputs.unsupported_required,
        all_critical_floors_pass=inputs.all_critical_floors_pass,
    )


@dataclass(frozen=True, slots=True)
class ReadinessInputs:
    raw_score: int
    qualified_band: QualifiedMatchBand
    confidence: ConfidenceState
    official_verification_current: bool
    selected_location_path_passes: bool = True
    compensation_verified: bool = True
    sponsorship_confirmed: bool = True
    employer_approved: bool = True
    role_scope_resolved: bool = True
    unsupported_required: bool = False
    notice_conflict_resolved: bool = True
    profile_current: bool = True
    facts_current: bool = True
    assessment_current: bool = True
    critical_floors_pass: bool = True
    employer_risk_current: bool = True


def ready_for_future_drafting(inputs: ReadinessInputs) -> bool:
    return (
        inputs.raw_score >= 85
        and inputs.qualified_band is QualifiedMatchBand.STRONG
        and inputs.confidence in {ConfidenceState.HIGH, ConfidenceState.MEDIUM}
        and inputs.official_verification_current
        and inputs.selected_location_path_passes
        and inputs.compensation_verified
        and inputs.sponsorship_confirmed
        and inputs.employer_approved
        and inputs.role_scope_resolved
        and not inputs.unsupported_required
        and inputs.notice_conflict_resolved
        and inputs.profile_current
        and inputs.facts_current
        and inputs.assessment_current
        and inputs.critical_floors_pass
        and inputs.employer_risk_current
    )


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


@dataclass(frozen=True, slots=True)
class ScoreRequirement:
    requirement_id: str
    kind: RequirementKind
    component: ScoringComponent
    mapping: RequirementEvidenceMapping

    def __post_init__(self) -> None:
        if not self.requirement_id.strip():
            raise ValueError("requirement ID is required")
        if self.mapping.requirement_id != self.requirement_id:
            raise ValueError("score requirement must bind its own requirement evidence mapping")

    @property
    def relation(self) -> EvidenceRelation:
        return self.mapping.relation


def component_anchor(requirements: tuple[ComponentRequirement, ...]) -> ComponentAnchor:
    if not requirements:
        return ComponentAnchor.NONE
    weights = {
        RequirementKind.REQUIRED: 3,
        RequirementKind.MATERIAL_RESPONSIBILITY: 2,
        RequirementKind.PREFERRED: 1,
    }
    total = sum(weights[requirement.kind] for requirement in requirements)
    direct_contribution = sum(
        weights[requirement.kind]
        for requirement in requirements
        if requirement.relation is EvidenceRelation.DIRECT
    )
    adjacent_contribution = sum(
        weights[requirement.kind]
        for requirement in requirements
        if requirement.relation is EvidenceRelation.ADJACENT
    )
    coverage = Fraction(direct_contribution * 2 + adjacent_contribution, total * 2)
    if coverage == 0:
        return ComponentAnchor.NONE
    if coverage < Fraction(35, 100):
        return ComponentAnchor.ADJACENT
    if coverage < Fraction(65, 100):
        return ComponentAnchor.PARTIAL
    if coverage < Fraction(85, 100):
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


def calculate_match_score(requirements: tuple[ScoreRequirement, ...]) -> MatchScoreComponents:
    """Derive the seven fixed component scores from validated requirement relations."""
    unique_requirements: dict[str, ScoreRequirement] = {}
    for requirement in requirements:
        existing = unique_requirements.get(requirement.requirement_id)
        if existing is not None and existing != requirement:
            raise ValueError("duplicate requirement has conflicting score inputs")
        unique_requirements[requirement.requirement_id] = requirement
    maxima = {
        ScoringComponent.ROLE: 20,
        ScoringComponent.DOMAIN: 20,
        ScoringComponent.RESPONSIBILITY: 20,
        ScoringComponent.TECHNICAL: 10,
        ScoringComponent.OUTCOME: 15,
        ScoringComponent.SENIORITY: 10,
        ScoringComponent.EVIDENCE: 5,
    }
    points = {
        component: anchor_points(
            maximum,
            component_anchor(
                tuple(
                    ComponentRequirement(
                        requirement.requirement_id,
                        requirement.kind,
                        requirement.relation,
                    )
                    for requirement in unique_requirements.values()
                    if requirement.component is component
                )
            ),
        )
        for component, maximum in maxima.items()
    }
    return MatchScoreComponents(
        role=points[ScoringComponent.ROLE],
        domain=points[ScoringComponent.DOMAIN],
        responsibility=points[ScoringComponent.RESPONSIBILITY],
        technical=points[ScoringComponent.TECHNICAL],
        outcome=points[ScoringComponent.OUTCOME],
        seniority=points[ScoringComponent.SENIORITY],
        evidence=points[ScoringComponent.EVIDENCE],
    )


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
