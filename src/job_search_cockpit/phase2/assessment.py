import re
from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
from uuid import uuid4

from sqlalchemy.orm import Session

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
from job_search_cockpit.phase2.models import (
    Phase2JobGateAssessment,
    Phase2JobRevision,
    Phase2LocationEligibilityPath,
    Phase2MatchAssessment,
    Phase2MatchComponent,
    Phase2RequirementMapping,
    Phase2ShortlistDecision,
)
from job_search_cockpit.phase2.mutation import Phase2MutationCoordinator
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
        if not 1 <= len(self.rubric_version.strip()) <= 64:
            raise ValueError("assessment rubric version must fit persisted metadata")
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

    def revalidate_matching_fact_set(
        self, expected: Phase1MatchingFactSetSnapshot
    ) -> Phase1MatchingFactSetSnapshot:
        try:
            return self._phase1_port.revalidate_matching_fact_set(expected)
        except (Phase1ContractUnavailable, ValueError) as error:
            raise AssessmentUnavailable("Assessment matching fact set changed.") from error


class AssessmentPublicationService:
    """Persists a fully validated local assessment only behind a fresh authority fence."""

    def __init__(
        self,
        authority_service: AssessmentAuthorityService,
        coordinator: Phase2MutationCoordinator,
    ) -> None:
        self._authority_service = authority_service
        self._coordinator = coordinator

    def publish(
        self,
        command: AssessmentPublicationCommand,
        *,
        expected_fact_set: Phase1MatchingFactSetSnapshot | None = None,
    ) -> str:
        expected = self._authority_service.capture_for_assessment()
        self._authority_service.revalidate_before_publication(expected)
        command.validate()
        self._validate_fact_set(command, expected_fact_set)

        def insert(session: Session) -> str:
            current = self._authority_service.revalidate_before_publication(expected)
            command.validate()
            self._validate_fact_set(command, expected_fact_set)
            if session.get(Phase2JobRevision, command.result.job_revision_id) is None:
                raise AssessmentUnavailable("Assessment job revision is unavailable.")
            fields = current.persistence_fields()
            gate_id = str(uuid4())
            session.add(
                Phase2JobGateAssessment(
                    id=gate_id,
                    job_revision_id=command.result.job_revision_id,
                    profile_fingerprint=current.phase1_inputs.profile.fingerprint,
                    result=command.gate_result.value,
                    reason_codes_json=list(command.gate_reason_codes),
                    **fields,
                )
            )
            for path in command.location_paths:
                session.add(
                    Phase2LocationEligibilityPath(
                        id=str(uuid4()),
                        job_gate_assessment_id=gate_id,
                        location_fingerprint=sha256(path.location_id.encode()).hexdigest(),
                        result=path.result.value,
                        reason_codes_json=list(path.reason_codes),
                        **fields,
                    )
                )
            assessment_id = command.result.assessment_id
            session.add(
                Phase2MatchAssessment(
                    id=assessment_id,
                    job_revision_id=command.result.job_revision_id,
                    job_gate_assessment_id=gate_id,
                    rubric_version=command.rubric_version,
                    coverage_ledger_fingerprint=command.coverage_ledger_fingerprint,
                    total_score=command.result.total_score,
                    qualified_band=command.result.qualified_band.value,
                    critical_floors_pass=command.result.critical_floors_pass,
                    meaningful_role_and_responsibility=command.result.meaningful_role_and_responsibility,
                    worthwhile_structure=command.result.worthwhile_structure,
                    unsupported_required=command.result.unsupported_required,
                    confidence=command.result.confidence.value,
                    assessment_state=command.assessment_state,
                    fact_set_fingerprint=command.fact_set_fingerprint,
                    **fields,
                )
            )
            for component, score in (
                (ScoringComponent.ROLE, command.result.components.role),
                (ScoringComponent.DOMAIN, command.result.components.domain),
                (ScoringComponent.RESPONSIBILITY, command.result.components.responsibility),
                (ScoringComponent.OUTCOME, command.result.components.outcome),
                (ScoringComponent.TECHNICAL, command.result.components.technical),
                (ScoringComponent.SENIORITY, command.result.components.seniority),
                (ScoringComponent.EVIDENCE, command.result.components.evidence),
            ):
                session.add(
                    Phase2MatchComponent(
                        id=str(uuid4()),
                        match_assessment_id=assessment_id,
                        component=component.value,
                        score=score,
                        **fields,
                    )
                )
            requirements = {
                requirement.requirement_id: requirement for requirement in command.requirements
            }
            for mapping in command.mappings:
                requirement = requirements[mapping.requirement_id]
                session.add(
                    Phase2RequirementMapping(
                        id=str(uuid4()),
                        match_assessment_id=assessment_id,
                        requirement_id=requirement.requirement_id,
                        requirement_kind=requirement.kind.value,
                        component=requirement.component.value,
                        source_span_id=requirement.source_span_id,
                        source_start_offset=requirement.start_offset,
                        source_end_offset=requirement.end_offset,
                        claim_id=mapping.claim_id,
                        fact_revision_id=mapping.revision_id,
                        support_assertion_id=mapping.support_assertion_id,
                        relation=mapping.relation.value,
                        reason_code=mapping.reason_code,
                        **fields,
                    )
                )
            session.add(
                Phase2ShortlistDecision(
                    id=str(uuid4()),
                    match_assessment_id=assessment_id,
                    decision=(
                        "focused" if command.result.focused_shortlist_eligible else "not_focused"
                    ),
                    reason_codes_json=list(command.shortlist_reason_codes),
                    **fields,
                )
            )
            return assessment_id

        return self._coordinator.run(insert, "publish_match_assessment")

    def _validate_fact_set(
        self,
        command: AssessmentPublicationCommand,
        expected_fact_set: Phase1MatchingFactSetSnapshot | None,
    ) -> None:
        """Reject publication when the exact Phase I selection drifts or is forged."""
        if expected_fact_set is None:
            return
        current = self._authority_service.revalidate_matching_fact_set(expected_fact_set)
        if (
            current != expected_fact_set
            or command.fact_set_fingerprint != expected_fact_set.fingerprint
        ):
            raise AssessmentUnavailable("Assessment matching fact set changed.")
        allowed = {
            (fact.requirement_id, fact.claim_id, fact.revision_id, fact.support_assertion_id)
            for fact in expected_fact_set.facts
        }
        for mapping in command.mappings:
            if mapping.relation is EvidenceRelation.NONE:
                continue
            if (
                mapping.requirement_id,
                mapping.claim_id,
                mapping.revision_id,
                mapping.support_assertion_id,
            ) not in allowed:
                raise AssessmentUnavailable("Assessment mapping is outside the approved fact set.")


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
