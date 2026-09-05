"""Current-candidate review and local-manual assessment orchestration.

This module deliberately treats listing text as public input and Phase I facts as
opaque choices.  It never infers a career fact, stores released wording, or
opens Phase I storage.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Literal, cast
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from job_search_cockpit.phase1_contract.service import (
    Phase1ContractService,
    Phase1ContractUnavailable,
)
from job_search_cockpit.phase1_contract.snapshots import (
    Phase1ActivationInputs,
    Phase1DisclosureAuthorizationRequest,
    Phase1DisclosureLifecycleRequest,
    Phase1DisclosurePayloadContext,
    Phase1FactDisclosureAuthorizationSnapshot,
    Phase1MatchingFactResolutionRequest,
    Phase1MatchingFactSnapshot,
    Phase1MatchingRequirementPredicate,
    Phase1MatchingRequirementQuery,
    Phase1MatchingRetrievalManifest,
    Phase1WordingReleaseRequest,
    canonical_fingerprint,
)
from job_search_cockpit.phase2.activation import Phase2ActivationService
from job_search_cockpit.phase2.assessment import (
    AssessmentAuthoritySnapshot,
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
    MatchScoreComponents,
    Requirement,
    RequirementEvidenceMapping,
    RequirementKind,
    ScoringComponent,
    resolve_qualified_match_band,
)
from job_search_cockpit.phase2.eligibility import JobGateInput, evaluate_excluded_employer
from job_search_cockpit.phase2.location_matching import (
    listing_supports_profile_location,
    select_profile_location,
)
from job_search_cockpit.phase2.models import (
    Phase2JobRevision,
    Phase2LocalManualMappingAttempt,
    Phase2LocalManualMappingAttemptEvent,
    Phase2MatchAssessment,
    Phase2MatchComponent,
    Phase2RequirementMapping,
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
_TerminalDisclosureState = Literal[
    "validated_response",
    "expired",
    "denied",
    "failed",
    "indeterminate",
    "cancelled",
]
_TERMINAL_DISCLOSURE_STATES = frozenset(
    {"validated_response", "expired", "denied", "failed", "indeterminate", "cancelled"}
)
_COMPONENT_NAMES = frozenset(
    {
        ScoringComponent.ROLE.value,
        ScoringComponent.DOMAIN.value,
        ScoringComponent.RESPONSIBILITY.value,
        ScoringComponent.TECHNICAL.value,
        ScoringComponent.OUTCOME.value,
        ScoringComponent.SENIORITY.value,
        ScoringComponent.EVIDENCE.value,
    }
)
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
    selected_location_path: str | None = None


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
    manifest: Phase1MatchingRetrievalManifest
    phase1_authorization_id: str
    phase1_authorization: Phase1FactDisclosureAuthorizationSnapshot
    authority: AssessmentAuthoritySnapshot
    logical_payload_digest: str
    expires_at: datetime
    # Public listing clauses are transient display data, never Phase I career wording.
    public_requirement_texts: tuple[tuple[str, str], ...] = ()


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
        authority = self._publication_service.capture_authority()
        if selected_location_path not in inputs.profile.payload.locations:
            raise CandidateWorkflowUnavailable("The selected location path is not eligible.")
        with self._coordinator._session_factory() as session:
            revision = session.get(Phase2JobRevision, job_revision_id)
            if revision is None or not _is_current(session, revision):
                raise CandidateWorkflowUnavailable("The job revision is not current.")
            if not listing_supports_profile_location(
                selected_location_path, revision.locations_json
            ):
                raise CandidateWorkflowUnavailable(
                    "The selected location path does not belong to the job revision."
                )
            review = _review(revision, inputs.profile.payload, True)
            if review.gate_result is not GateResult.PASS:
                raise CandidateWorkflowUnavailable(
                    "The candidate has blocking or unresolved gates."
                )
            requirements = extract_public_requirements(revision, bounded=True)
        if not requirements:
            raise CandidateWorkflowUnavailable(
                "The public job description has no assessable clauses."
            )
        if len(requirements) > 8:
            requirements = requirements[:8]
        coverage = canonical_fingerprint([_requirement_payload(item) for item in requirements])
        attempt_id, nonce = str(uuid4()), str(uuid4())
        preflight_scope_fingerprint = canonical_fingerprint(
            {
                "scope_version": "phase2.local-manual-preflight.v1",
                "job_revision_id": revision.id,
                "coverage_ledger_fingerprint": coverage,
                "phase1_profile_generation": inputs.profile.active_profile_generation,
                "phase1_authority_generation": inputs.readiness.authority_high_water_mark,
                "phase1_restore_generation": inputs.readiness.restore_generation,
                "phase2_activation_generation": view.activation_generation,
                "phase2_restore_generation": view.restore_generation,
            }
        )
        query = _matching_query(
            revision.id, coverage, preflight_scope_fingerprint, requirements
        )
        try:
            manifest = self._phase1_port.matching_retrieval_manifest(query)
            if not manifest.complete and len(requirements) > 1:
                end = len(requirements) - 1
                while end >= 1:
                    chunk = requirements[:end]
                    chunk_coverage = canonical_fingerprint(
                        [_requirement_payload(item) for item in chunk]
                    )
                    chunk_preflight = canonical_fingerprint(
                        {
                            "scope_version": "phase2.local-manual-preflight.v1",
                            "job_revision_id": revision.id,
                            "coverage_ledger_fingerprint": chunk_coverage,
                            "phase1_profile_generation": inputs.profile.active_profile_generation,
                            "phase1_authority_generation": inputs.readiness.authority_high_water_mark,
                            "phase1_restore_generation": inputs.readiness.restore_generation,
                            "phase2_activation_generation": view.activation_generation,
                            "phase2_restore_generation": view.restore_generation,
                        }
                    )
                    chunk_query = _matching_query(
                        revision.id, chunk_coverage, chunk_preflight, chunk
                    )
                    chunk_manifest = self._phase1_port.matching_retrieval_manifest(chunk_query)
                    if chunk_manifest.complete:
                        requirements = chunk
                        coverage = chunk_coverage
                        preflight_scope_fingerprint = chunk_preflight
                        query = chunk_query
                        manifest = chunk_manifest
                        break
                    end -= 1
            if (
                self._phase1_port.revalidate_matching_retrieval_manifest(manifest) != manifest
                or not manifest.complete
            ):
                raise CandidateWorkflowUnavailable("The approved fact set is incomplete.")
        except (Phase1ContractUnavailable, ValueError) as error:
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
        digest = Phase1ContractService.disclosure_payload_digest(manifest, context)
        # The append-only Phase II attempt and its recovery witness are the
        # prerequisite for Phase I authorization and wording release.
        self._record_attempt(
            attempt_id,
            nonce,
            attempt_id,
            revision.id,
            selected_location_path,
            coverage,
            manifest.fingerprint,
            digest,
            expires_at,
            inputs,
            view,
        )
        try:
            authorization = self._phase1_port.authorize_matching_disclosure(
                Phase1DisclosureAuthorizationRequest(context=context, logical_payload_digest=digest)
            )
        except Exception as error:
            self._settle_initial_failure(
                attempt_id, digest, "indeterminate", "phase1_authorization_unavailable"
            )
            raise CandidateWorkflowUnavailable(
                "The local mapping authorization could not be started safely."
            ) from error
        if authorization.state != "authorized" or authorization.authorization_id != attempt_id:
            self._settle_initial_failure(
                attempt_id, digest, "denied", "phase1_authorization_rejected"
            )
            raise CandidateWorkflowUnavailable("The disclosure authorization is unavailable.")
        try:
            release = self._phase1_port.release_matching_wording(
                Phase1WordingReleaseRequest(
                    authorization=authorization, attempt_id=attempt_id, nonce=nonce
                )
            )
        except Exception as error:
            self._settle_initial_failure(
                attempt_id, digest, "indeterminate", "phase1_release_unavailable"
            )
            raise CandidateWorkflowUnavailable(
                "The local mapping authorization could not be started safely."
            ) from error
        if release.logical_payload_digest != digest:
            self._settle_initial_failure(
                attempt_id, digest, "failed", "phase1_release_digest_mismatch"
            )
            raise CandidateWorkflowUnavailable(
                "The released choices do not match the authorization."
            )
        if release.manifest_fingerprint != manifest.fingerprint:
            self._settle_initial_failure(
                attempt_id, digest, "failed", "phase1_release_manifest_mismatch"
            )
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
            self._settle_initial_failure(
                attempt_id, digest, "failed", "phase1_release_wording_hash_mismatch"
            )
            raise CandidateWorkflowUnavailable(
                "Released wording does not match the approved manifest."
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
            manifest,
            authorization.authorization_id,
            authorization,
            authority,
            digest,
            expires_at,
            tuple(
                (
                    requirement.requirement_id,
                    revision.public_description[
                        requirement.start_offset : requirement.end_offset
                    ].strip(),
                )
                for requirement in requirements
            ),
        )

    def publish_local_manual_mapping(
        self, launch: LocalManualMappingLaunch, selections: tuple[LocalManualMappingSelection, ...]
    ) -> str:
        """Consume once, recovering conservatively across the two independent stores."""
        recovered = self._reconcile_publication(launch)
        if recovered is not None:
            return recovered
        if self._now() >= launch.expires_at:
            terminal = self._record_phase1_terminal(launch, "expired", "authorization_expired")
            self._terminal(launch.attempt_id, terminal, "authorization_expired")
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
            (edge.requirement_id, choice.claim_id, choice.revision_id, choice.support_assertion_id)
            for edge in launch.manifest.edges
            for choice in launch.manifest.choices
            if choice.claim_id == edge.claim_id
        }
        for mapping in mappings:
            if (
                mapping.relation is not EvidenceRelation.NONE
                and (
                    mapping.requirement_id,
                    mapping.claim_id,
                    mapping.revision_id,
                    mapping.support_assertion_id,
                )
                not in allowed
            ):
                raise CandidateWorkflowUnavailable(
                    "The selected evidence choice is not authorized for this job."
                )
        with self._coordinator._session_factory() as session:
            revision = session.get(Phase2JobRevision, launch.job_revision_id)
            if revision is None or not _is_current(session, revision):
                raise CandidateWorkflowUnavailable("The job revision is not current.")
            if not listing_supports_profile_location(
                launch.selected_location_path, revision.locations_json
            ):
                raise CandidateWorkflowUnavailable(
                    "The selected location does not belong to this job."
                )
            current_requirements = extract_public_requirements(revision, bounded=True)
            if len(current_requirements) > len(launch.requirements):
                current_requirements = current_requirements[: len(launch.requirements)]
        if current_requirements != launch.requirements:
            raise CandidateWorkflowUnavailable("The job requirements changed before publication.")
        query = launch.manifest.query
        manifest = self._phase1_port.matching_retrieval_manifest(query)
        if (
            not manifest.complete
            or manifest.fingerprint != launch.manifest_fingerprint
            or self._phase1_port.revalidate_matching_retrieval_manifest(manifest) != manifest
        ):
            raise CandidateWorkflowUnavailable("The approved fact set changed before publication.")
        assessment_id = _assessment_id(launch)
        self._record_publication_intent(launch, assessment_id)
        try:
            canonical_fact_keys = self._resolve_canonical_fact_keys(launch, mappings)
        except (Phase1ContractUnavailable, ValueError) as error:
            raise CandidateWorkflowUnavailable("The approved evidence is unavailable.") from error
        try:
            lifecycle = self._phase1_port.record_disclosure_lifecycle(
                Phase1DisclosureLifecycleRequest(
                    authorization_id=launch.phase1_authorization_id,
                    logical_payload_digest=launch.logical_payload_digest,
                    state="consuming",
                )
            )
        except Exception:
            recovered = self._settle_failed_publication(launch)
            if recovered is not None:
                return recovered
            raise
        if lifecycle.state != "consuming":
            self._settle_non_consuming_phase1(launch, lifecycle.state)
            raise CandidateWorkflowUnavailable(
                "The Phase I disclosure did not enter consuming state."
            )
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
                assessment_id,
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
                launch.manifest.fingerprint,
                "stable",
                ("local_manual_mapping",),
                canonical_fact_keys,
            )
            assessment_id = self._publication_service.publish(
                command,
                expected_manifest=launch.manifest,
                expected_authority=launch.authority,
                publication_guard=lambda session: _publication_guard(
                    session, launch, assessment_id, self._now()
                ),
            )
        except Exception:
            with self._coordinator._session_factory() as session:
                published = session.get(Phase2MatchAssessment, assessment_id)
            if published is not None:
                recovered = self._reconcile_publication(launch)
                if recovered is not None:
                    return recovered
                raise CandidateWorkflowUnavailable(
                    "The local mapping publication witness is inconsistent."
                ) from None
            recovered = self._settle_failed_publication(launch)
            if recovered is not None:
                return recovered
            raise
        if self._record_phase1_terminal(launch, "validated_response", "") != "validated_response":
            raise CandidateWorkflowUnavailable(
                "The Phase I disclosure terminal state does not match publication."
            )
        return assessment_id

    def _resolve_canonical_fact_keys(
        self,
        launch: LocalManualMappingLaunch,
        mappings: tuple[RequirementEvidenceMapping, ...],
    ) -> tuple[tuple[str, str], ...]:
        supported = tuple(
            Phase1MatchingFactSnapshot(
                requirement_id=item.requirement_id,
                claim_id=cast(str, item.claim_id),
                revision_id=cast(str, item.revision_id),
                support_assertion_id=cast(str, item.support_assertion_id),
            )
            for item in mappings
            if item.relation is not EvidenceRelation.NONE
        )
        if not supported:
            return ()
        resolved = self._phase1_port.resolve_released_matching_facts(
            Phase1MatchingFactResolutionRequest(
                authorization=launch.phase1_authorization, facts=supported
            )
        )
        expected = {
            (item.requirement_id, item.claim_id, item.revision_id, item.support_assertion_id)
            for item in supported
        }
        actual = {
            (item.requirement_id, item.claim_id, item.revision_id, item.support_assertion_id)
            for item in resolved
        }
        if actual != expected or any(item.canonical_key.startswith("job.") for item in resolved):
            raise CandidateWorkflowUnavailable("The approved evidence is unavailable.")
        return tuple((item.requirement_id, item.canonical_key) for item in resolved)

    def _reconcile_publication(self, launch: LocalManualMappingLaunch) -> str | None:
        record, state = self._attempt(launch)
        assessment_id = _assessment_id(launch)
        with self._coordinator._session_factory() as session:
            published = session.get(Phase2MatchAssessment, assessment_id)
            witness_valid = published is not None and _is_publication_witness(
                session, published, launch
            )
        if published is not None:
            if not witness_valid:
                raise CandidateWorkflowUnavailable(
                    "The local mapping publication witness is inconsistent."
                )
            if state in {"authorized", "consuming"}:
                # A committed assessment is the decisive Phase II publication witness.
                # Recover an interrupted attempt by appending its missing terminal
                # event; never try to publish it a second time.
                self._terminal(
                    launch.attempt_id,
                    "validated_response",
                    "assessment_published_reconciliation",
                )
                _record, state = self._attempt(launch)
            if state != "validated_response":
                raise CandidateWorkflowUnavailable(
                    "The local mapping publication witness has an invalid terminal state."
                )
            if (
                self._record_phase1_terminal(launch, "validated_response", "")
                != "validated_response"
            ):
                raise CandidateWorkflowUnavailable(
                    "The Phase I disclosure terminal state does not match publication."
                )
            return assessment_id
        intent = self._publication_intent(launch)
        if state == "authorized" and not intent:
            return None
        if state == "validated_response":
            raise CandidateWorkflowUnavailable(
                "The local mapping publication witness is inconsistent."
            )
        if state in {"authorized", "consuming"}:
            desired: _TerminalDisclosureState = (
                "expired" if self._now() >= launch.expires_at else "indeterminate"
            )
            state = self._record_phase1_terminal(launch, desired, "publication_interrupted")
            self._terminal(launch.attempt_id, state, "publication_interrupted")
        if state in {
            "expired",
            "denied",
            "failed",
            "indeterminate",
            "cancelled",
        }:
            self._record_phase1_terminal(launch, cast(_TerminalDisclosureState, state), "")
            raise CandidateWorkflowUnavailable(
                "The local mapping authorization cannot be replayed."
            )
        raise CandidateWorkflowUnavailable(
            f"The local mapping attempt has an invalid recovery state: {state or record.id}."
        )

    def _settle_failed_publication(self, launch: LocalManualMappingLaunch) -> str | None:
        _record, state = self._attempt(launch)
        if state == "validated_response":
            return self._reconcile_publication(launch)
        terminal: _TerminalDisclosureState = (
            "expired" if self._now() >= launch.expires_at else "failed"
        )
        terminal = self._record_phase1_terminal(launch, terminal, "publication_failed")
        self._terminal(launch.attempt_id, terminal, "publication_failed")
        return None

    def _settle_non_consuming_phase1(self, launch: LocalManualMappingLaunch, state: str) -> None:
        if state in _TERMINAL_DISCLOSURE_STATES - {"validated_response"}:
            self._terminal(launch.attempt_id, state, "phase1_consuming_rejected")
            return
        desired: _TerminalDisclosureState = (
            "expired" if self._now() >= launch.expires_at else "indeterminate"
        )
        if state not in _TERMINAL_DISCLOSURE_STATES:
            desired = self._record_phase1_terminal(launch, desired, "phase1_consuming_rejected")
        self._terminal(
            launch.attempt_id,
            "indeterminate" if desired == "validated_response" else desired,
            "phase1_consuming_rejected",
        )

    def _record_phase1_terminal(
        self, launch: LocalManualMappingLaunch, state: _TerminalDisclosureState, reason: str
    ) -> _TerminalDisclosureState:
        lifecycle = self._phase1_port.record_disclosure_lifecycle(
            Phase1DisclosureLifecycleRequest(
                authorization_id=launch.phase1_authorization_id,
                logical_payload_digest=launch.logical_payload_digest,
                state=state,
                reason_code=reason,
            )
        )
        if lifecycle.state not in _TERMINAL_DISCLOSURE_STATES:
            raise CandidateWorkflowUnavailable("The Phase I disclosure terminal state is invalid.")
        return cast(_TerminalDisclosureState, lifecycle.state)

    def _attempt(
        self, launch: LocalManualMappingLaunch
    ) -> tuple[Phase2LocalManualMappingAttempt, str | None]:
        with self._coordinator._session_factory() as session:
            record = session.scalar(
                select(Phase2LocalManualMappingAttempt).where(
                    Phase2LocalManualMappingAttempt.attempt_id == launch.attempt_id
                )
            )
            if (
                record is None
                or record.logical_payload_digest != launch.logical_payload_digest
                or record.phase1_authorization_id != launch.phase1_authorization_id
                or record.manifest_fingerprint != launch.manifest_fingerprint
            ):
                raise CandidateWorkflowUnavailable(
                    "The local mapping authorization binding changed."
                )
            return record, _attempt_state(session, record.id)

    def _record_publication_intent(
        self, launch: LocalManualMappingLaunch, assessment_id: str
    ) -> None:
        if self._publication_intent(launch):
            raise CandidateWorkflowUnavailable(
                "The local mapping publication intent cannot be replayed."
            )
        self._coordinator.recovery_ledger.append(
            RecoveryEvent(
                f"local-manual-publication-{launch.attempt_id}",
                "local_manual_mapping_publication_intent",
                {
                    "attempt_id": launch.attempt_id,
                    "phase1_authorization_id": launch.phase1_authorization_id,
                    "logical_payload_digest": launch.logical_payload_digest,
                    "manifest_fingerprint": launch.manifest_fingerprint,
                    "assessment_id": assessment_id,
                },
                self._now(),
            )
        )

    def _publication_intent(self, launch: LocalManualMappingLaunch) -> bool:
        expected = {
            "attempt_id": launch.attempt_id,
            "phase1_authorization_id": launch.phase1_authorization_id,
            "logical_payload_digest": launch.logical_payload_digest,
            "manifest_fingerprint": launch.manifest_fingerprint,
            "assessment_id": _assessment_id(launch),
        }
        events = tuple(
            entry.event
            for entry in self._coordinator.recovery_ledger.read_all()
            if entry.event.event_type == "local_manual_mapping_publication_intent"
            and entry.event.payload.get("attempt_id") == launch.attempt_id
        )
        if not events:
            return False
        if len(events) != 1 or events[0].payload != expected:
            raise CandidateWorkflowUnavailable(
                "The local mapping publication recovery record is invalid."
            )
        return True

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

    def _settle_initial_failure(
        self,
        attempt_id: str,
        logical_payload_digest: str,
        desired: _TerminalDisclosureState,
        reason: str,
    ) -> None:
        """Seal a persisted launch when Phase I authorization or release is uncertain."""
        terminal = desired
        try:
            lifecycle = self._phase1_port.record_disclosure_lifecycle(
                Phase1DisclosureLifecycleRequest(
                    authorization_id=attempt_id,
                    logical_payload_digest=logical_payload_digest,
                    state=desired,
                    reason_code=reason,
                )
            )
            if lifecycle.state in _TERMINAL_DISCLOSURE_STATES:
                terminal = cast(_TerminalDisclosureState, lifecycle.state)
            else:
                terminal = "indeterminate"
        except Exception:
            terminal = "indeterminate"
        # The Phase II terminal event is the durable no-replay boundary.
        # A ledger append failure must still leave the user with a bounded error.
        with suppress(Exception):
            self._terminal(attempt_id, terminal, reason)

    def _terminal(self, attempt_id: str, state: str, reason: str) -> None:
        def terminal(session: Session) -> bool:
            record = session.scalar(
                select(Phase2LocalManualMappingAttempt).where(
                    Phase2LocalManualMappingAttempt.attempt_id == attempt_id
                )
            )
            if record is None or _attempt_state(session, record.id) not in {
                "authorized",
                "consuming",
            }:
                return False
            sequence = (
                int(
                    session.scalar(
                        select(func.count(Phase2LocalManualMappingAttemptEvent.id)).where(
                            Phase2LocalManualMappingAttemptEvent.attempt_id == record.id
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
            return True

        if self._coordinator.run(terminal, f"local_manual_mapping_{state}"):
            self._coordinator.recovery_ledger.append(
                RecoveryEvent(
                    str(uuid4()),
                    "local_manual_mapping_terminal",
                    {"attempt_id": attempt_id, "state": state, "reason_code": reason},
                    self._now(),
                )
            )


def extract_public_requirements(
    revision: Phase2JobRevision,
    *,
    bounded: bool = False,
) -> tuple[Requirement, ...]:
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
    if len(requirements) > 32:
        if bounded:
            scored: list[tuple[int, int, Requirement]] = []
            for i, r in enumerate(requirements):
                weight = (
                    3
                    if r.kind is RequirementKind.REQUIRED
                    else 2
                    if r.kind is RequirementKind.MATERIAL_RESPONSIBILITY
                    else 1
                )
                scored.append((weight, -i, r))
            scored.sort(reverse=True)
            selected = [r for _, _, r in scored[:32]]
            selected.sort(key=lambda r: r.start_offset)
            return tuple(selected)
        raise CandidateWorkflowUnavailable(
            "The public job description exceeds the 32-requirement mapping budget."
        )
    return tuple(requirements)


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
    revision_id: str,
    coverage: str,
    preflight_scope_fingerprint: str,
    requirements: tuple[Requirement, ...],
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
        launch_session_fingerprint=preflight_scope_fingerprint,
        requirements=predicates,
    )


def _review(
    revision: Phase2JobRevision, profile: SearchProfilePayload, current: bool
) -> CandidateReview:
    reasons: list[str] = []
    gate = GateResult.PASS
    selected_location_path = select_profile_location(revision.locations_json, profile.locations)
    if not revision.public_description.strip():
        gate, reasons = GateResult.FAIL, ["missing_public_description"]
    elif (
        evaluate_excluded_employer(profile, JobGateInput(revision.employer_name)) is GateResult.FAIL
    ):
        gate, reasons = GateResult.FAIL, ["excluded_employer"]
    elif selected_location_path is None:
        gate, reasons = GateResult.FAIL, ["no_eligible_location"]
    elif not _is_approved_role_title(revision.title, profile.eligible_roles):
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
        selected_location_path,
    )


def _is_approved_role_title(title: str, eligible_roles: tuple[str, ...]) -> bool:
    return any(
        title == role or (title.startswith(f"{role} (") and title.endswith(")"))
        for role in eligible_roles
    )


def _is_current(session: Session, revision: Phase2JobRevision) -> bool:
    current = session.scalar(
        select(Phase2JobRevision.id)
        .where(Phase2JobRevision.job_record_id == revision.job_record_id)
        .order_by(Phase2JobRevision.created_at.desc(), Phase2JobRevision.id.desc())
    )
    return current == revision.id


def _attempt_state(session: Session, attempt_id: str) -> str | None:
    return session.scalar(
        select(Phase2LocalManualMappingAttemptEvent.state)
        .where(Phase2LocalManualMappingAttemptEvent.attempt_id == attempt_id)
        .order_by(Phase2LocalManualMappingAttemptEvent.sequence.desc())
    )


def _assessment_id(launch: LocalManualMappingLaunch) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            f"phase2-local-manual-assessment:{launch.attempt_id}:{launch.logical_payload_digest}",
        )
    )


def _is_publication_witness(
    session: Session, assessment: Phase2MatchAssessment, launch: LocalManualMappingLaunch
) -> bool:
    if (
        assessment.job_revision_id != launch.job_revision_id
        or assessment.rubric_version != _RUBRIC_VERSION
        or assessment.coverage_ledger_fingerprint
        != canonical_fingerprint([_requirement_payload(item) for item in launch.requirements])
        or assessment.fact_set_fingerprint != launch.manifest_fingerprint
        or assessment.assessment_state != "stable"
    ):
        return False
    if any(
        getattr(assessment, field) != value
        for field, value in launch.authority.persistence_fields().items()
    ):
        return False
    mappings = tuple(
        session.scalars(
            select(Phase2RequirementMapping).where(
                Phase2RequirementMapping.match_assessment_id == assessment.id
            )
        )
    )
    expected = {item.requirement_id: item for item in launch.requirements}
    if len(mappings) != len(expected) or {item.requirement_id for item in mappings} != set(
        expected
    ):
        return False
    allowed = {
        (edge.requirement_id, choice.claim_id, choice.revision_id, choice.support_assertion_id)
        for edge in launch.manifest.edges
        for choice in launch.manifest.choices
        if choice.claim_id == edge.claim_id
    }
    validated_mappings: list[RequirementEvidenceMapping] = []
    for mapping in mappings:
        requirement = expected[mapping.requirement_id]
        if any(
            getattr(mapping, field) != value
            for field, value in launch.authority.persistence_fields().items()
        ):
            return False
        try:
            relation = EvidenceRelation(mapping.relation)
            validated_mapping = RequirementEvidenceMapping(
                mapping.requirement_id,
                relation,
                mapping.reason_code,
                mapping.claim_id,
                mapping.fact_revision_id,
                mapping.support_assertion_id,
            )
        except ValueError:
            return False
        if (
            mapping.requirement_kind != requirement.kind.value
            or mapping.component != requirement.component.value
            or mapping.source_span_id != requirement.source_span_id
            or mapping.source_start_offset != requirement.start_offset
            or mapping.source_end_offset != requirement.end_offset
        ):
            return False
        if (
            relation is not EvidenceRelation.NONE
            and (
                mapping.requirement_id,
                mapping.claim_id,
                mapping.fact_revision_id,
                mapping.support_assertion_id,
            )
            not in allowed
        ):
            return False
        validated_mappings.append(validated_mapping)
    try:
        scored = tuple(
            ScoreRequirement(
                requirement.requirement_id,
                requirement.kind,
                requirement.component,
                next(
                    mapping
                    for mapping in validated_mappings
                    if mapping.requirement_id == requirement.requirement_id
                ),
            )
            for requirement in launch.requirements
        )
        expected_components = _component_scores(calculate_match_score(scored))
    except ValueError:
        return False
    unsupported = any(
        requirement.kind is RequirementKind.REQUIRED
        and next(
            mapping
            for mapping in validated_mappings
            if mapping.requirement_id == requirement.requirement_id
        ).relation
        is EvidenceRelation.NONE
        for requirement in launch.requirements
    )
    floors = (
        expected_components[ScoringComponent.ROLE.value] >= 10
        and expected_components[ScoringComponent.RESPONSIBILITY.value] >= 10
    )
    total_score = sum(expected_components.values())
    worthwhile = total_score >= 70
    if (
        assessment.total_score != total_score
        or assessment.qualified_band
        != resolve_qualified_match_band(
            raw_score=total_score,
            meaningful_role_and_responsibility=floors,
            worthwhile_structure=worthwhile,
            unsupported_required=unsupported,
            all_critical_floors_pass=floors,
        ).value
        or assessment.critical_floors_pass != floors
        or assessment.meaningful_role_and_responsibility != floors
        or assessment.worthwhile_structure != worthwhile
        or assessment.unsupported_required != unsupported
        or assessment.confidence
        != resolve_confidence(("required_clause_uncertain",) if unsupported else ()).value
    ):
        return False
    component_rows = tuple(
        session.scalars(
            select(Phase2MatchComponent).where(
                Phase2MatchComponent.match_assessment_id == assessment.id
            )
        )
    )
    component_names = tuple(row.component for row in component_rows)
    if (
        len(component_rows) != len(_COMPONENT_NAMES)
        or len(set(component_names)) != len(component_names)
        or set(component_names) != _COMPONENT_NAMES
    ):
        return False
    for row in component_rows:
        if row.score != expected_components[row.component]:
            return False
        if any(
            getattr(row, field) != value
            for field, value in launch.authority.persistence_fields().items()
        ):
            return False
    return True


def _component_scores(components: MatchScoreComponents) -> dict[str, int]:
    return {
        ScoringComponent.ROLE.value: components.role,
        ScoringComponent.DOMAIN.value: components.domain,
        ScoringComponent.RESPONSIBILITY.value: components.responsibility,
        ScoringComponent.TECHNICAL.value: components.technical,
        ScoringComponent.OUTCOME.value: components.outcome,
        ScoringComponent.SENIORITY.value: components.seniority,
        ScoringComponent.EVIDENCE.value: components.evidence,
    }


def _publication_guard(
    session: Session,
    launch: LocalManualMappingLaunch,
    assessment_id: str,
    now: datetime,
) -> None:
    revision = session.get(Phase2JobRevision, launch.job_revision_id)
    if revision is None or not _is_current(session, revision):
        raise CandidateWorkflowUnavailable("The job revision is not current.")
    if not listing_supports_profile_location(
        launch.selected_location_path, revision.locations_json
    ):
        raise CandidateWorkflowUnavailable("The selected location does not belong to this job.")
    current_requirements = extract_public_requirements(revision, bounded=True)
    if len(current_requirements) > len(launch.requirements):
        current_requirements = current_requirements[: len(launch.requirements)]
    if current_requirements != launch.requirements:
        raise CandidateWorkflowUnavailable("The job requirements changed before publication.")
    record = session.scalar(
        select(Phase2LocalManualMappingAttempt).where(
            Phase2LocalManualMappingAttempt.attempt_id == launch.attempt_id
        )
    )
    state = _attempt_state(session, record.id) if record is not None else None
    expires_at = record.expires_at if record is not None else now
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if (
        record is None
        or state != "authorized"
        or record.logical_payload_digest != launch.logical_payload_digest
        or record.phase1_authorization_id != launch.phase1_authorization_id
        or record.manifest_fingerprint != launch.manifest_fingerprint
        or expires_at <= now
        or session.get(Phase2MatchAssessment, assessment_id) is not None
    ):
        raise CandidateWorkflowUnavailable("The local mapping authorization cannot be replayed.")
    session.add_all(
        (
            Phase2LocalManualMappingAttemptEvent(
                id=str(uuid4()),
                attempt_id=record.id,
                sequence=2,
                state="consuming",
                reason_code="",
            ),
            Phase2LocalManualMappingAttemptEvent(
                id=str(uuid4()),
                attempt_id=record.id,
                sequence=3,
                state="validated_response",
                reason_code="assessment_published",
            ),
        )
    )


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
