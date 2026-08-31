"""Current-candidate review and local-manual assessment orchestration.

This module deliberately treats listing text as public input and Phase I facts as
opaque choices.  It never infers a career fact, stores released wording, or
opens Phase I storage.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from job_search_cockpit.phase1_contract.snapshots import (
    Phase1ActivationInputs,
    Phase1DisclosureAuthorizationRequest,
    Phase1DisclosurePayloadContext,
    Phase1MatchingRequirementPredicate,
    Phase1MatchingRequirementQuery,
    Phase1WordingReleaseRequest,
    canonical_fingerprint,
)
from job_search_cockpit.phase2.activation import Phase2ActivationService
from job_search_cockpit.phase2.assessment import (
    AssessmentPublicationCommand,
    AssessmentPublicationService,
    ScoreRequirement,
    calculate_match_score,
    resolve_confidence,
)
from job_search_cockpit.phase2.assessment_types import (
    ConfidenceState,
    EvidenceRelation,
    GateResult,
    LocationEligibilityPath,
    MatchAssessmentResult,
    Requirement,
    RequirementEvidenceMapping,
    RequirementKind,
    ScoringComponent,
    resolve_qualified_match_band,
)
from job_search_cockpit.phase2.eligibility import JobGateInput, evaluate_excluded_employer
from job_search_cockpit.phase2.models import (
    Phase2JobRevision,
    Phase2LocalManualMappingAttempt,
    Phase2LocalManualMappingAttemptEvent,
)
from job_search_cockpit.phase2.mutation import Phase2MutationCoordinator
from job_search_cockpit.phase2.recovery_ledger import RecoveryEvent
from job_search_cockpit.phase2.types import Phase2Action, Phase2ActivationView
from job_search_cockpit.ports import Phase1MatchingPort
from job_search_cockpit.search_profile.catalog import SearchProfilePayload


class CandidateWorkflowUnavailable(ValueError):
    """Raised when a current candidate cannot safely be assessed."""


_TTL = timedelta(minutes=15)
_RUBRIC_VERSION = "phase2-fixed-score.v1"
_RESPONSE_SCHEMA_VERSION = "phase2.local-manual-mapping.v1"
_RETRIEVAL_CONFIGURATION_VERSION = "phase1.matching-retrieval.v1"
_INTERPRETER_CONFIGURATION_VERSION = "local_manual.v1"
_RELATION_REASONS = {
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


@dataclass(frozen=True, slots=True)
class CandidateReview:
    job_revision_id: str
    title: str
    employer_name: str
    locations: tuple[str, ...]
    gate_result: GateResult
    gate_reason_codes: tuple[str, ...]
    confidence: ConfidenceState
    current: bool


@dataclass(frozen=True, slots=True)
class LocalManualMappingLaunch:
    attempt_id: str
    nonce: str
    job_revision_id: str
    selected_location_path: str
    requirements: tuple[Requirement, ...]
    # This is display-only and is intentionally never persisted by Phase II.
    choices: tuple[tuple[str, str, str, str, str], ...]
    manifest_fingerprint: str
    logical_payload_digest: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class LocalManualMappingSelection:
    requirement_id: str
    relation: EvidenceRelation
    reason_code: str
    claim_id: str | None = None
    revision_id: str | None = None
    support_assertion_id: str | None = None

    def mapping(self) -> RequirementEvidenceMapping:
        return RequirementEvidenceMapping(
            self.requirement_id,
            self.relation,
            self.reason_code,
            self.claim_id,
            self.revision_id,
            self.support_assertion_id,
        )


class CandidateWorkflowService:
    def __init__(
        self,
        phase1_port: Phase1MatchingPort,
        activation_service: Phase2ActivationService,
        coordinator: Phase2MutationCoordinator,
        publication_service: AssessmentPublicationService,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._phase1_port = phase1_port
        self._activation_service = activation_service
        self._coordinator = coordinator
        self._publication_service = publication_service
        self._now = now or (lambda: datetime.now(UTC))

    def current_candidates(self) -> tuple[CandidateReview, ...]:
        inputs = self._phase1_port.activation_inputs()
        self._activation_service.revalidate_before(Phase2Action.SCORING)
        with self._coordinator._session_factory() as session:
            revisions = session.scalars(select(Phase2JobRevision)).all()
            return tuple(
                _review(revision, inputs.profile.payload, True)
                for revision in sorted(
                    revisions, key=lambda item: (item.created_at, item.id), reverse=True
                )
                if _is_current(session, revision)
            )

    def begin_local_manual_mapping(
        self, job_revision_id: str, selected_location_path: str
    ) -> LocalManualMappingLaunch:
        inputs = self._phase1_port.activation_inputs()
        view = self._activation_service.revalidate_before(Phase2Action.SCORING)
        if selected_location_path not in inputs.profile.payload.locations:
            raise CandidateWorkflowUnavailable("The selected location path is not eligible.")
        with self._coordinator._session_factory() as session:
            revision = session.get(Phase2JobRevision, job_revision_id)
            if revision is None or not _is_current(session, revision):
                raise CandidateWorkflowUnavailable("The job revision is not current.")
            review = _review(revision, inputs.profile.payload, True)
            if review.gate_result is not GateResult.PASS:
                raise CandidateWorkflowUnavailable(
                    "The candidate has blocking or unresolved gates."
                )
            requirements = extract_public_requirements(revision)
        if not requirements or any(
            item.kind is RequirementKind.REQUIRED and item.component is ScoringComponent.EVIDENCE
            for item in requirements
        ):
            raise CandidateWorkflowUnavailable("The job has an uncertain mandatory requirement.")
        coverage = canonical_fingerprint([_requirement_payload(item) for item in requirements])
        attempt_id, nonce = str(uuid4()), str(uuid4())
        query = _matching_query(revision.id, coverage, nonce, requirements)
        try:
            manifest = self._phase1_port.matching_retrieval_manifest(query)
            if (
                self._phase1_port.revalidate_matching_retrieval_manifest(manifest) != manifest
                or not manifest.complete
            ):
                raise CandidateWorkflowUnavailable("The approved fact set is incomplete.")
        except ValueError as error:
            raise CandidateWorkflowUnavailable("The approved fact set is unavailable.") from error
        expires_at = self._now() + _TTL
        context = Phase1DisclosurePayloadContext(
            packet_id=attempt_id,
            attempt_id=attempt_id,
            nonce=nonce,
            phase2_authorization_id=attempt_id,
            manifest_fingerprint=manifest.fingerprint,
            job_revision_id=revision.id,
            selected_location_path=(selected_location_path,),
            coverage_ledger_fingerprint=coverage,
            validated_requirements_fingerprint=coverage,
            rubric_fingerprint=canonical_fingerprint({"version": _RUBRIC_VERSION}),
            retrieval_configuration_version=_RETRIEVAL_CONFIGURATION_VERSION,
            interpreter_configuration_version=_INTERPRETER_CONFIGURATION_VERSION,
            response_schema_version=_RESPONSE_SCHEMA_VERSION,
            phase1_profile_generation=inputs.profile.active_profile_generation,
            phase1_readiness_generation=inputs.readiness.readiness_generation,
            phase1_authority_generation=inputs.readiness.authority_high_water_mark,
            phase1_restore_generation=inputs.readiness.restore_generation,
            disclosure_budget_epoch=manifest.disclosure_budget_epoch,
            disclosure_policy_generation=manifest.disclosure_policy_generation,
            phase2_activation_generation=view.activation_generation,
            phase2_restore_generation=view.restore_generation,
            issued_at=self._now(),
            expires_at=expires_at,
            allowed_relations=("direct", "adjacent", "none"),
            allowed_reason_codes=tuple(
                sorted({code for codes in _RELATION_REASONS.values() for code in codes})
            ),
        )
        digest = canonical_fingerprint(context)
        authorization = self._phase1_port.authorize_matching_disclosure(
            Phase1DisclosureAuthorizationRequest(context=context, logical_payload_digest=digest)
        )
        if authorization.state != "authorized":
            raise CandidateWorkflowUnavailable("The disclosure authorization is unavailable.")
        release = self._phase1_port.release_matching_wording(
            Phase1WordingReleaseRequest(
                authorization=authorization, attempt_id=attempt_id, nonce=nonce
            )
        )
        if (
            release.logical_payload_digest != digest
            or release.manifest_fingerprint != manifest.fingerprint
        ):
            raise CandidateWorkflowUnavailable(
                "The released choices do not match the authorization."
            )
        hashes = {
            (item.claim_id, item.revision_id, item.support_assertion_id): item.safe_wording_sha256
            for item in manifest.choices
        }
        if any(
            hashes.get((item.claim_id, item.revision_id, item.support_assertion_id))
            != item.safe_wording_sha256
            for item in release.choices
        ):
            raise CandidateWorkflowUnavailable(
                "Released wording does not match the approved manifest."
            )
        self._record_attempt(
            attempt_id,
            nonce,
            authorization.authorization_id,
            revision.id,
            selected_location_path,
            coverage,
            manifest.fingerprint,
            digest,
            expires_at,
            inputs,
            view,
        )
        return LocalManualMappingLaunch(
            attempt_id,
            nonce,
            revision.id,
            selected_location_path,
            requirements,
            tuple(
                (
                    item.canonical_key,
                    item.claim_id,
                    item.revision_id,
                    item.support_assertion_id,
                    item.safe_wording,
                )
                for item in release.choices
            ),
            manifest.fingerprint,
            digest,
            expires_at,
        )

    def publish_local_manual_mapping(
        self, launch: LocalManualMappingLaunch, selections: tuple[LocalManualMappingSelection, ...]
    ) -> str:
        """Atomically consume a locally authorized response before publication."""
        if self._now() >= launch.expires_at:
            self._terminal(launch.attempt_id, "expired", "authorization_expired")
            raise CandidateWorkflowUnavailable("The local mapping authorization expired.")
        mappings = tuple(item.mapping() for item in selections)
        requirements = {item.requirement_id: item for item in launch.requirements}
        if set(requirements) != {item.requirement_id for item in mappings} or len(mappings) != len(
            requirements
        ):
            raise CandidateWorkflowUnavailable(
                "Every current requirement needs exactly one mapping."
            )
        allowed = {
            (claim, revision, support)
            for _key, claim, revision, support, _wording in launch.choices
        }
        for mapping in mappings:
            if (
                mapping.relation is not EvidenceRelation.NONE
                and (mapping.claim_id, mapping.revision_id, mapping.support_assertion_id)
                not in allowed
            ):
                raise CandidateWorkflowUnavailable(
                    "The selected evidence choice is not authorized for this job."
                )
        coverage = canonical_fingerprint(
            [_requirement_payload(item) for item in launch.requirements]
        )
        query = _matching_query(launch.job_revision_id, coverage, launch.nonce, launch.requirements)
        manifest = self._phase1_port.matching_retrieval_manifest(query)
        if (
            not manifest.complete
            or manifest.fingerprint != launch.manifest_fingerprint
            or self._phase1_port.revalidate_matching_retrieval_manifest(manifest) != manifest
        ):
            raise CandidateWorkflowUnavailable("The approved fact set changed before publication.")
        self._consume(launch.attempt_id, launch.logical_payload_digest)
        try:
            scored = tuple(
                ScoreRequirement(
                    item.requirement_id,
                    item.kind,
                    item.component,
                    next(
                        mapping
                        for mapping in mappings
                        if mapping.requirement_id == item.requirement_id
                    ),
                )
                for item in launch.requirements
            )
            components = calculate_match_score(scored)
            unsupported = any(
                item.kind is RequirementKind.REQUIRED
                and next(
                    mapping for mapping in mappings if mapping.requirement_id == item.requirement_id
                ).relation
                is EvidenceRelation.NONE
                for item in launch.requirements
            )
            floors = components.role >= 10 and components.responsibility >= 10
            result = MatchAssessmentResult(
                str(uuid4()),
                launch.job_revision_id,
                components,
                resolve_qualified_match_band(
                    raw_score=components.total,
                    meaningful_role_and_responsibility=components.role >= 10
                    and components.responsibility >= 10,
                    worthwhile_structure=components.total >= 70,
                    unsupported_required=unsupported,
                    all_critical_floors_pass=floors,
                ),
                resolve_confidence(("required_clause_uncertain",) if unsupported else ()),
                True,
                True,
                floors,
                components.role >= 10 and components.responsibility >= 10,
                components.total >= 70,
                unsupported,
            )
            command = AssessmentPublicationCommand(
                result,
                launch.requirements,
                mappings,
                GateResult.PASS,
                ("profile_gate_pass",),
                (
                    LocationEligibilityPath(
                        launch.selected_location_path, GateResult.PASS, ("profile_location",)
                    ),
                ),
                _RUBRIC_VERSION,
                canonical_fingerprint([_requirement_payload(item) for item in launch.requirements]),
                launch.logical_payload_digest,
                "stable",
                ("local_manual_mapping",),
            )
            assessment_id = self._publication_service.publish(command)
        except Exception:
            self._terminal(launch.attempt_id, "failed", "publication_failed")
            raise
        self._terminal(launch.attempt_id, "validated_response", "")
        return assessment_id

    def _record_attempt(
        self,
        attempt_id: str,
        nonce: str,
        phase1_authorization_id: str,
        revision_id: str,
        location: str,
        coverage: str,
        manifest: str,
        digest: str,
        expires_at: datetime,
        inputs: Phase1ActivationInputs,
        view: Phase2ActivationView,
    ) -> None:
        fields = {
            "phase1_profile_fingerprint": inputs.profile.fingerprint,
            "phase1_profile_generation": inputs.profile.active_profile_generation,
            "phase1_readiness_fingerprint": inputs.readiness.fingerprint,
            "phase1_readiness_generation": inputs.readiness.readiness_generation,
            "phase1_authority_fingerprint": inputs.acceptance_receipt.fingerprint,
            "phase1_authority_generation": inputs.readiness.authority_high_water_mark,
            "phase1_restore_generation": inputs.readiness.restore_generation,
            "phase2_activation_generation": view.activation_generation,
            "phase2_restore_generation": view.restore_generation,
        }

        def write(session: Session) -> None:
            record = Phase2LocalManualMappingAttempt(
                id=str(uuid4()),
                attempt_id=attempt_id,
                nonce_sha256=sha256(nonce.encode()).hexdigest(),
                phase1_authorization_id=phase1_authorization_id,
                job_revision_id=revision_id,
                selected_location_path_fingerprint=canonical_fingerprint({"location": location}),
                coverage_ledger_fingerprint=coverage,
                manifest_fingerprint=manifest,
                logical_payload_digest=digest,
                rubric_version=_RUBRIC_VERSION,
                retrieval_configuration_version=_RETRIEVAL_CONFIGURATION_VERSION,
                interpreter_configuration_version=_INTERPRETER_CONFIGURATION_VERSION,
                response_schema_version=_RESPONSE_SCHEMA_VERSION,
                expires_at=expires_at,
                **fields,
            )
            session.add(record)
            session.add(
                Phase2LocalManualMappingAttemptEvent(
                    id=str(uuid4()),
                    attempt_id=record.id,
                    sequence=1,
                    state="authorized",
                    reason_code="",
                )
            )

        self._coordinator.run(write, "authorize_local_manual_mapping")
        self._coordinator.recovery_ledger.append(
            RecoveryEvent(
                str(uuid4()),
                "local_manual_mapping_authorized",
                {
                    "attempt_id": attempt_id,
                    "logical_payload_digest": digest,
                    "manifest_fingerprint": manifest,
                },
                self._now(),
            )
        )

    def _consume(self, attempt_id: str, digest: str) -> None:
        def consume(session: Session) -> None:
            record = session.scalar(
                select(Phase2LocalManualMappingAttempt).where(
                    Phase2LocalManualMappingAttempt.attempt_id == attempt_id
                )
            )
            if (
                record is None
                or record.state != "authorized"
                or record.logical_payload_digest != digest
                or record.expires_at <= self._now()
            ):
                raise CandidateWorkflowUnavailable(
                    "The local mapping authorization cannot be replayed."
                )
            record.state = "consuming"
            session.add(
                Phase2LocalManualMappingAttemptEvent(
                    id=str(uuid4()),
                    attempt_id=record.id,
                    sequence=2,
                    state="consuming",
                    reason_code="",
                )
            )

        self._coordinator.run(consume, "consume_local_manual_mapping")

    def _terminal(self, attempt_id: str, state: str, reason: str) -> None:
        def terminal(session: Session) -> None:
            record = session.scalar(
                select(Phase2LocalManualMappingAttempt).where(
                    Phase2LocalManualMappingAttempt.attempt_id == attempt_id
                )
            )
            if record is None or record.state not in {"authorized", "consuming"}:
                return
            record.state = state
            sequence = (
                int(
                    session.scalar(
                        select(
                            func.count(Phase2LocalManualMappingAttemptEvent.id).where(
                                Phase2LocalManualMappingAttemptEvent.attempt_id == record.id
                            )
                        )
                    )
                    or 0
                )
                + 1
            )
            session.add(
                Phase2LocalManualMappingAttemptEvent(
                    id=str(uuid4()),
                    attempt_id=record.id,
                    sequence=sequence,
                    state=state,
                    reason_code=reason,
                )
            )

        self._coordinator.run(terminal, f"local_manual_mapping_{state}")


def extract_public_requirements(revision: Phase2JobRevision) -> tuple[Requirement, ...]:
    """Deterministically cite every sentence; uncertain clauses fail closed downstream."""
    description = revision.public_description.strip()
    if not description:
        raise CandidateWorkflowUnavailable("A public job description is required.")
    requirements: list[Requirement] = []
    for index, match in enumerate(re.finditer(r"[^.!?\n]+", description)):
        text = match.group().strip()
        if not text:
            continue
        kind = _kind(text)
        component = _component(text)
        normalized = " ".join(text.casefold().split())
        clause_digest = sha256((str(index) + normalized).encode()).hexdigest()[:16]
        requirement_id = f"job.{revision.id}.requirement.{clause_digest}"
        requirements.append(
            Requirement(
                requirement_id,
                kind,
                component,
                f"job.{revision.id}.span.{index}",
                match.start(),
                match.end(),
            )
        )
    if not requirements:
        raise CandidateWorkflowUnavailable("The public job description has no assessable clauses.")
    return tuple(requirements[:32])


def _kind(text: str) -> RequirementKind:
    value = text.casefold()
    if any(marker in value for marker in ("must", "required", "minimum", "qualification")):
        return RequirementKind.REQUIRED
    if any(marker in value for marker in ("you will", "responsible for", "own ")):
        return RequirementKind.MATERIAL_RESPONSIBILITY
    if any(marker in value for marker in ("preferred", "nice to have", "bonus")):
        return RequirementKind.PREFERRED
    return (
        RequirementKind.REQUIRED
    )  # unknown public clauses are conservative mandatory requirements


def _component(text: str) -> ScoringComponent:
    value = text.casefold()
    groups = (
        (ScoringComponent.TECHNICAL, ("api", "data", "platform", "integration", "ai")),
        (ScoringComponent.DOMAIN, ("fintech", "lending", "banking", "commerce", "payment")),
        (ScoringComponent.RESPONSIBILITY, ("roadmap", "delivery", "discovery", "priorit")),
        (ScoringComponent.OUTCOME, ("kpi", "outcome", "scale", "revenue")),
        (ScoringComponent.SENIORITY, ("senior", "lead", "years", "manager")),
        (ScoringComponent.ROLE, ("product", "role", "title")),
    )
    matches = [component for component, terms in groups if any(term in value for term in terms)]
    return matches[0] if len(matches) == 1 else ScoringComponent.EVIDENCE


def _matching_query(
    revision_id: str, coverage: str, nonce: str, requirements: tuple[Requirement, ...]
) -> Phase1MatchingRequirementQuery:
    taxonomy = {
        ScoringComponent.ROLE: ("role_profile.senior_product_manager",),
        ScoringComponent.DOMAIN: ("domain.fintech",),
        ScoringComponent.RESPONSIBILITY: ("responsibility.product_decisions",),
        ScoringComponent.TECHNICAL: ("technical_object.platform",),
        ScoringComponent.OUTCOME: ("outcome_scale.kpi",),
        ScoringComponent.SENIORITY: ("role_profile.senior_product_manager",),
        ScoringComponent.EVIDENCE: ("capability.product_delivery",),
    }
    predicates = tuple(
        Phase1MatchingRequirementPredicate(
            requirement_id=item.requirement_id,
            component=item.component.value,
            modality=(
                "required"
                if item.kind is RequirementKind.REQUIRED
                else "material_responsibility"
                if item.kind is RequirementKind.MATERIAL_RESPONSIBILITY
                else "preferred"
            ),
            capability_ids=taxonomy[item.component]
            if item.component is ScoringComponent.EVIDENCE
            else (),
            responsibility_ids=taxonomy[item.component]
            if item.component is ScoringComponent.RESPONSIBILITY
            else (),
            domain_ids=taxonomy[item.component]
            if item.component is ScoringComponent.DOMAIN
            else (),
            technical_object_ids=taxonomy[item.component]
            if item.component is ScoringComponent.TECHNICAL
            else (),
            outcome_scale_ids=taxonomy[item.component]
            if item.component is ScoringComponent.OUTCOME
            else (),
            role_profile_ids=taxonomy[item.component]
            if item.component in {ScoringComponent.ROLE, ScoringComponent.SENIORITY}
            else (),
        )
        for item in requirements
    )
    return Phase1MatchingRequirementQuery(
        requirement_ids=tuple(item.requirement_id for item in requirements),
        job_revision_id=revision_id,
        coverage_ledger_fingerprint=coverage,
        launch_session_fingerprint=sha256(nonce.encode()).hexdigest(),
        requirements=predicates,
    )


def _review(
    revision: Phase2JobRevision, profile: SearchProfilePayload, current: bool
) -> CandidateReview:
    reasons: list[str] = []
    gate = GateResult.PASS
    if not revision.public_description.strip():
        gate, reasons = GateResult.FAIL, ["missing_public_description"]
    elif (
        evaluate_excluded_employer(profile, JobGateInput(revision.employer_name)) is GateResult.FAIL
    ):
        gate, reasons = GateResult.FAIL, ["excluded_employer"]
    elif not set(str(item) for item in revision.locations_json) & set(profile.locations):
        gate, reasons = GateResult.FAIL, ["no_eligible_location"]
    elif revision.title not in profile.eligible_roles:
        gate, reasons = GateResult.UNKNOWN, ["role_requires_manual_review"]
    return CandidateReview(
        revision.id,
        revision.title,
        revision.employer_name,
        tuple(str(item) for item in revision.locations_json),
        gate,
        tuple(reasons or ["profile_gate_pass"]),
        ConfidenceState.HIGH if gate is GateResult.PASS else ConfidenceState.BLOCKED,
        current,
    )


def _is_current(session: Session, revision: Phase2JobRevision) -> bool:
    current = session.scalar(
        select(Phase2JobRevision.id)
        .where(Phase2JobRevision.job_record_id == revision.job_record_id)
        .order_by(Phase2JobRevision.created_at.desc(), Phase2JobRevision.id.desc())
    )
    return current == revision.id


def _requirement_payload(item: Requirement) -> dict[str, object]:
    return {
        "id": item.requirement_id,
        "kind": item.kind.value,
        "component": item.component.value,
        "span": item.source_span_id,
        "start": item.start_offset,
        "end": item.end_offset,
    }


__all__ = [
    "CandidateReview",
    "CandidateWorkflowService",
    "CandidateWorkflowUnavailable",
    "LocalManualMappingLaunch",
    "LocalManualMappingSelection",
    "extract_public_requirements",
]
