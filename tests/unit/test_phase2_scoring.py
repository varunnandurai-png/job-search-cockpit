import pytest

from job_search_cockpit.phase1_contract.snapshots import (
    Phase1MatchingFactSetSnapshot,
    Phase1MatchingFactSnapshot,
    Phase1ResumeFactProjection,
)
from job_search_cockpit.phase2.assessment import (
    AssessmentEvidenceService,
    AssessmentUnavailable,
    ComponentContribution,
    ComponentRequirement,
    QualifiedBandInputs,
    ReadinessInputs,
    anchor_points,
    calculate_component_score,
    component_anchor,
    qualified_match_band,
    ready_for_future_drafting,
    resolve_confidence,
)
from job_search_cockpit.phase2.assessment_types import (
    ComponentAnchor,
    ConfidenceState,
    EvidenceRelation,
    GateResult,
    MatchScoreComponents,
    QualifiedMatchBand,
    RequirementKind,
)


def test_match_score_components_total_the_approved_maximum() -> None:
    components = MatchScoreComponents(
        role=20,
        domain=20,
        responsibility=20,
        technical=10,
        outcome=15,
        seniority=10,
        evidence=5,
    )

    assert components.total == 100


def test_match_score_components_reject_a_component_above_its_approved_maximum() -> None:
    with pytest.raises(ValueError, match="role score exceeds its approved maximum"):
        MatchScoreComponents(
            role=21,
            domain=20,
            responsibility=20,
            technical=10,
            outcome=15,
            seniority=10,
            evidence=5,
        )


def test_assessment_states_are_bounded_to_the_approved_vocabulary() -> None:
    assert GateResult.PASS.value == "pass"
    assert RequirementKind.REQUIRED.value == "required"
    assert EvidenceRelation.ADJACENT.value == "adjacent"
    assert ConfidenceState.BLOCKED.value == "blocked"


def test_component_score_caps_duplicate_evidence_at_its_fixed_maximum() -> None:
    score = calculate_component_score(
        20,
        (
            ComponentContribution("requirement-1", 20, EvidenceRelation.DIRECT),
            ComponentContribution("requirement-1", 20, EvidenceRelation.DIRECT),
            ComponentContribution("requirement-2", 20, EvidenceRelation.DIRECT),
        ),
    )

    assert score == 20


def test_component_anchor_requires_two_direct_requirements_for_close() -> None:
    anchor = component_anchor(
        (
            ComponentRequirement("role.one", RequirementKind.REQUIRED, EvidenceRelation.DIRECT),
            ComponentRequirement(
                "role.two", RequirementKind.MATERIAL_RESPONSIBILITY, EvidenceRelation.DIRECT
            ),
        )
    )

    assert anchor is ComponentAnchor.CLOSE


def test_single_direct_requirement_is_capped_at_strong() -> None:
    anchor = component_anchor(
        (ComponentRequirement("role.one", RequirementKind.REQUIRED, EvidenceRelation.DIRECT),)
    )

    assert anchor is ComponentAnchor.STRONG


def test_component_anchor_uses_exact_rational_threshold_at_thirty_five_percent() -> None:
    requirements = tuple(
        ComponentRequirement(f"required-{index}", RequirementKind.REQUIRED, EvidenceRelation.NONE)
        if index >= 2
        else ComponentRequirement(
            f"required-{index}", RequirementKind.REQUIRED, EvidenceRelation.DIRECT
        )
        for index in range(4)
    ) + tuple(
        ComponentRequirement(
            f"preferred-{index}",
            RequirementKind.PREFERRED,
            EvidenceRelation.DIRECT if index == 0 else EvidenceRelation.NONE,
        )
        for index in range(8)
    )

    assert component_anchor(requirements) is ComponentAnchor.PARTIAL


def test_anchor_points_use_only_the_approved_discrete_values() -> None:
    assert anchor_points(20, ComponentAnchor.STRONG) == 15
    assert anchor_points(15, ComponentAnchor.PARTIAL) == 8
    assert anchor_points(10, ComponentAnchor.ADJACENT) == 3
    assert anchor_points(5, ComponentAnchor.CLOSE) == 5


def test_confidence_is_low_for_unlisted_or_high_severity_reasons() -> None:
    assert resolve_confidence(("required_clause_uncertain",)) is ConfidenceState.LOW
    assert resolve_confidence(("unexpected_reason",)) is ConfidenceState.LOW


def test_confidence_is_medium_only_for_preferred_uncertainty() -> None:
    assert resolve_confidence(("preferred_clause_uncertain",)) is ConfidenceState.MEDIUM


def test_high_raw_score_with_a_required_gap_is_not_strong() -> None:
    band = qualified_match_band(
        QualifiedBandInputs(
            raw_score=90,
            meaningful_role_and_responsibility=True,
            worthwhile_structure=True,
            unsupported_required=True,
            all_critical_floors_pass=True,
        )
    )

    assert band is QualifiedMatchBand.WORTHWHILE_WITH_REQUIRED_GAP


def test_future_drafting_readiness_rejects_a_strong_score_with_stale_verification() -> None:
    ready = ready_for_future_drafting(
        ReadinessInputs(
            raw_score=90,
            qualified_band=QualifiedMatchBand.STRONG,
            confidence=ConfidenceState.HIGH,
            official_verification_current=False,
        )
    )

    assert ready is False


def test_evidence_service_blocks_a_projection_with_an_unmet_requirement() -> None:
    projection = Phase1ResumeFactProjection(
        requirement_ids=("role.product",),
        facts=(),
        profile_fingerprint="a" * 64,
        profile_generation=1,
        readiness_fingerprint="b" * 64,
        readiness_generation=1,
        authority_fingerprint="c" * 64,
        authority_generation=1,
        restore_generation=0,
        fingerprint="d" * 64,
    )

    service = AssessmentEvidenceService(_ProjectionPort(projection))

    with pytest.raises(AssessmentUnavailable, match="approved evidence"):
        service.require_complete_evidence(("role.product",))


def test_matching_fact_set_drift_blocks_scoring_evidence() -> None:
    snapshot = Phase1MatchingFactSetSnapshot(
        requirement_ids=("role.product",),
        facts=(
            Phase1MatchingFactSnapshot(
                requirement_id="role.product",
                claim_id="claim-1",
                revision_id="revision-1",
                support_assertion_id="support-1",
            ),
        ),
        profile_fingerprint="a" * 64,
        profile_generation=1,
        readiness_fingerprint="b" * 64,
        readiness_generation=1,
        authority_fingerprint="c" * 64,
        authority_generation=1,
        restore_generation=0,
        fingerprint="d" * 64,
    )
    service = AssessmentEvidenceService(_MatchingFactSetPort(snapshot))

    with pytest.raises(AssessmentUnavailable, match="matching fact set changed"):
        service.require_complete_matching_facts(("role.product",))


class _ProjectionPort:
    def __init__(self, projection: Phase1ResumeFactProjection) -> None:
        self.projection = projection

    def resume_fact_projection(self, _request: object) -> Phase1ResumeFactProjection:
        return self.projection

    def revalidate_resume_fact_projection(
        self, _expected: Phase1ResumeFactProjection
    ) -> Phase1ResumeFactProjection:
        return self.projection


class _MatchingFactSetPort:
    def __init__(self, snapshot: Phase1MatchingFactSetSnapshot) -> None:
        self.snapshot = snapshot

    def matching_fact_set(self, _query: object) -> Phase1MatchingFactSetSnapshot:
        return self.snapshot

    def revalidate_matching_fact_set(
        self, expected: Phase1MatchingFactSetSnapshot
    ) -> Phase1MatchingFactSetSnapshot:
        return expected.model_copy(update={"fingerprint": "e" * 64})
