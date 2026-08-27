import pytest

from job_search_cockpit.phase1_contract.snapshots import (
    Phase1MatchingFactSetSnapshot,
    Phase1MatchingFactSnapshot,
    Phase1ResumeFactProjection,
)
from job_search_cockpit.phase2.assessment import (
    AssessmentEvidenceService,
    AssessmentPublicationCommand,
    AssessmentUnavailable,
    ComponentContribution,
    ComponentRequirement,
    QualifiedBandInputs,
    ReadinessInputs,
    ScoreRequirement,
    anchor_points,
    calculate_component_score,
    calculate_match_score,
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
    MatchAssessmentResult,
    MatchScoreComponents,
    QualifiedMatchBand,
    Requirement,
    RequirementEvidenceMapping,
    RequirementKind,
    ScoringComponent,
)


def _score_requirement(
    requirement_id: str,
    kind: RequirementKind,
    component: ScoringComponent,
    relation: EvidenceRelation,
) -> ScoreRequirement:
    identifiers = (
        {}
        if relation is EvidenceRelation.NONE
        else {
            "claim_id": f"claim-{requirement_id}",
            "revision_id": f"revision-{requirement_id}",
            "support_assertion_id": f"support-{requirement_id}",
        }
    )
    return ScoreRequirement(
        requirement_id,
        kind,
        component,
        RequirementEvidenceMapping(
            requirement_id=requirement_id,
            relation=relation,
            reason_code=(
                "none/no_approved_evidence_found"
                if relation is EvidenceRelation.NONE
                else "direct/exact_capability_performed"
                if relation is EvidenceRelation.DIRECT
                else "adjacent/approved_taxonomy_neighbor"
            ),
            **identifiers,
        ),
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


def test_match_result_rejects_an_identifier_too_large_to_persist() -> None:
    with pytest.raises(
        ValueError, match="assessment and job revision IDs must fit persisted metadata"
    ):
        MatchAssessmentResult(
            assessment_id="a" * 37,
            job_revision_id="revision-1",
            components=MatchScoreComponents(20, 20, 20, 10, 15, 10, 5),
            qualified_band=QualifiedMatchBand.STRONG,
            confidence=ConfidenceState.HIGH,
            hard_gates_pass=True,
            current=True,
            critical_floors_pass=True,
            meaningful_role_and_responsibility=True,
            worthwhile_structure=True,
            unsupported_required=False,
        )


def test_assessment_states_are_bounded_to_the_approved_vocabulary() -> None:
    assert GateResult.PASS.value == "pass"
    assert RequirementKind.REQUIRED.value == "required"
    assert EvidenceRelation.ADJACENT.value == "adjacent"
    assert ConfidenceState.BLOCKED.value == "blocked"


def test_requirement_evidence_mapping_refuses_claimed_support_without_exact_fact_ids() -> None:
    requirement = Requirement(
        requirement_id="requirements.product-roadmap",
        kind=RequirementKind.REQUIRED,
        component=ScoringComponent.RESPONSIBILITY,
        source_span_id="span-1",
        start_offset=0,
        end_offset=24,
    )

    with pytest.raises(ValueError, match="exact Phase I fact identifiers"):
        RequirementEvidenceMapping(
            requirement_id=requirement.requirement_id,
            relation=EvidenceRelation.DIRECT,
                reason_code="direct/exact_capability_performed",
        )


def test_requirement_evidence_mapping_rejects_an_unlisted_reason_code() -> None:
    with pytest.raises(ValueError, match="mapping reason code is not approved"):
        RequirementEvidenceMapping(
            requirement_id="requirements.product-role",
            relation=EvidenceRelation.DIRECT,
            reason_code="direct/unverified_claim",
            claim_id="claim-1",
            revision_id="revision-1",
            support_assertion_id="support-1",
        )


def test_score_requirement_rejects_a_mapping_for_a_different_requirement() -> None:
    mapping = RequirementEvidenceMapping(
        requirement_id="requirements.other-role",
        relation=EvidenceRelation.DIRECT,
        reason_code="direct/exact_capability_performed",
        claim_id="claim-1",
        revision_id="revision-1",
        support_assertion_id="support-1",
    )

    with pytest.raises(ValueError, match="must bind its own requirement evidence mapping"):
        ScoreRequirement(
            "requirements.product-role",
            RequirementKind.REQUIRED,
            ScoringComponent.ROLE,
            mapping,
        )


def test_publication_command_rejects_a_mapping_without_a_published_requirement() -> None:
    requirement = Requirement(
        requirement_id="requirements.product-role",
        kind=RequirementKind.REQUIRED,
        component=ScoringComponent.ROLE,
        source_span_id="span-1",
        start_offset=0,
        end_offset=12,
    )
    command = AssessmentPublicationCommand(
        result=MatchAssessmentResult(
            assessment_id="assessment-1",
            job_revision_id="revision-1",
            components=MatchScoreComponents(20, 20, 20, 10, 15, 10, 5),
            qualified_band=QualifiedMatchBand.STRONG,
            confidence=ConfidenceState.HIGH,
            hard_gates_pass=True,
            current=True,
            critical_floors_pass=True,
            meaningful_role_and_responsibility=True,
            worthwhile_structure=True,
            unsupported_required=False,
        ),
        requirements=(requirement,),
        mappings=(
            RequirementEvidenceMapping(
                requirement_id="requirements.other-role",
                relation=EvidenceRelation.NONE,
                reason_code="none/no_approved_evidence_found",
            ),
        ),
        gate_result=GateResult.PASS,
        gate_reason_codes=("eligible_role",),
        location_paths=(),
        rubric_version="rubric-v1",
        coverage_ledger_fingerprint="a" * 64,
        fact_set_fingerprint="b" * 64,
        assessment_state="stable",
        shortlist_reason_codes=("qualified_match",),
    )

    with pytest.raises(ValueError, match="published requirement"):
        command.validate()


def test_publication_command_rejects_a_rubric_version_too_large_to_persist() -> None:
    requirement = Requirement(
        requirement_id="requirements.product-role",
        kind=RequirementKind.REQUIRED,
        component=ScoringComponent.ROLE,
        source_span_id="span-1",
        start_offset=0,
        end_offset=12,
    )
    command = AssessmentPublicationCommand(
        result=MatchAssessmentResult(
            assessment_id="assessment-1",
            job_revision_id="revision-1",
            components=MatchScoreComponents(20, 20, 20, 10, 15, 10, 5),
            qualified_band=QualifiedMatchBand.STRONG,
            confidence=ConfidenceState.HIGH,
            hard_gates_pass=True,
            current=True,
            critical_floors_pass=True,
            meaningful_role_and_responsibility=True,
            worthwhile_structure=True,
            unsupported_required=False,
        ),
        requirements=(requirement,),
        mappings=(
            RequirementEvidenceMapping(
                requirement_id=requirement.requirement_id,
                relation=EvidenceRelation.NONE,
                reason_code="none/no_approved_evidence_found",
            ),
        ),
        gate_result=GateResult.PASS,
        gate_reason_codes=("eligible_role",),
        location_paths=(),
        rubric_version="r" * 65,
        coverage_ledger_fingerprint="a" * 64,
        fact_set_fingerprint="b" * 64,
        assessment_state="stable",
        shortlist_reason_codes=("qualified_match",),
    )

    with pytest.raises(ValueError, match="rubric version must fit persisted metadata"):
        command.validate()


def test_blocked_confidence_cannot_enter_the_focused_shortlist_at_any_score() -> None:
    result = MatchAssessmentResult(
        assessment_id="assessment-1",
        job_revision_id="revision-1",
        components=MatchScoreComponents(
            role=20,
            domain=20,
            responsibility=20,
            technical=10,
            outcome=15,
            seniority=10,
            evidence=5,
        ),
        qualified_band=QualifiedMatchBand.STRONG,
        confidence=ConfidenceState.BLOCKED,
        hard_gates_pass=True,
        current=True,
        critical_floors_pass=True,
        meaningful_role_and_responsibility=True,
        worthwhile_structure=True,
        unsupported_required=False,
    )

    assert result.total_score == 100
    assert result.focused_shortlist_eligible is False


def test_match_result_rejects_a_strong_band_below_the_strong_score_floor() -> None:
    with pytest.raises(ValueError, match="strong band requires a raw score of at least 85"):
        MatchAssessmentResult(
            assessment_id="assessment-1",
            job_revision_id="revision-1",
            components=MatchScoreComponents(
                role=20,
                domain=20,
                responsibility=20,
                technical=10,
                outcome=10,
                seniority=0,
                evidence=0,
            ),
            qualified_band=QualifiedMatchBand.STRONG,
            confidence=ConfidenceState.HIGH,
            hard_gates_pass=True,
            current=True,
            critical_floors_pass=True,
            meaningful_role_and_responsibility=True,
            worthwhile_structure=True,
            unsupported_required=False,
        )


def test_match_result_rejects_a_strong_band_when_a_critical_floor_fails() -> None:
    with pytest.raises(ValueError, match="strong band requires all critical component floors"):
        MatchAssessmentResult(
            assessment_id="assessment-1",
            job_revision_id="revision-1",
            components=MatchScoreComponents(
                role=20,
                domain=20,
                responsibility=20,
                technical=10,
                outcome=15,
                seniority=10,
                evidence=5,
            ),
            qualified_band=QualifiedMatchBand.STRONG,
            confidence=ConfidenceState.HIGH,
            hard_gates_pass=True,
            current=True,
            critical_floors_pass=False,
            meaningful_role_and_responsibility=True,
            worthwhile_structure=True,
            unsupported_required=False,
        )


def test_match_result_rejects_a_band_that_contradicts_its_structural_inputs() -> None:
    with pytest.raises(ValueError, match="qualified band does not match its score inputs"):
        MatchAssessmentResult(
            assessment_id="assessment-1",
            job_revision_id="revision-1",
            components=MatchScoreComponents(
                role=20,
                domain=20,
                responsibility=20,
                technical=10,
                outcome=15,
                seniority=10,
                evidence=5,
            ),
            qualified_band=QualifiedMatchBand.STRONG,
            confidence=ConfidenceState.HIGH,
            hard_gates_pass=True,
            current=True,
            critical_floors_pass=True,
            meaningful_role_and_responsibility=True,
            worthwhile_structure=False,
            unsupported_required=False,
        )


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


def test_fixed_calculator_derives_component_points_from_locked_anchors() -> None:
    components = calculate_match_score(
        (
            _score_requirement(
                "role.one", RequirementKind.REQUIRED, ScoringComponent.ROLE, EvidenceRelation.DIRECT
            ),
            _score_requirement(
                "role.two", RequirementKind.REQUIRED, ScoringComponent.ROLE, EvidenceRelation.DIRECT
            ),
            _score_requirement(
                "responsibility.one",
                RequirementKind.MATERIAL_RESPONSIBILITY,
                ScoringComponent.RESPONSIBILITY,
                EvidenceRelation.DIRECT,
            ),
        )
    )

    assert components.role == 20
    assert components.responsibility == 15
    assert components.total == 35


def test_fixed_calculator_does_not_promote_duplicate_requirement_to_close_anchor() -> None:
    components = calculate_match_score(
        (
            _score_requirement(
                "role.one", RequirementKind.REQUIRED, ScoringComponent.ROLE, EvidenceRelation.DIRECT
            ),
            _score_requirement(
                "role.one", RequirementKind.REQUIRED, ScoringComponent.ROLE, EvidenceRelation.DIRECT
            ),
        )
    )

    assert components.role == 15


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


def test_matching_fact_set_rejects_duplicate_evidence_for_one_requirement() -> None:
    snapshot = Phase1MatchingFactSetSnapshot(
        requirement_ids=("role.product",),
        facts=(
            Phase1MatchingFactSnapshot(
                requirement_id="role.product",
                claim_id="claim-1",
                revision_id="revision-1",
                support_assertion_id="support-1",
            ),
            Phase1MatchingFactSnapshot(
                requirement_id="role.product",
                claim_id="claim-2",
                revision_id="revision-2",
                support_assertion_id="support-2",
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
    service = AssessmentEvidenceService(_StableMatchingFactSetPort(snapshot))

    with pytest.raises(AssessmentUnavailable, match="matching fact set is malformed"):
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


class _StableMatchingFactSetPort(_MatchingFactSetPort):
    def revalidate_matching_fact_set(
        self, expected: Phase1MatchingFactSetSnapshot
    ) -> Phase1MatchingFactSetSnapshot:
        return expected
