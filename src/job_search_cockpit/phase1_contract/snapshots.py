import json
import re
from datetime import datetime
from hashlib import sha256
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from job_search_cockpit.search_profile.catalog import SearchProfilePayload


def _json_default(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    raise TypeError(f"Cannot fingerprint {type(value).__name__}")


def canonical_fingerprint(payload: object) -> str:
    encoded = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
    canonical = json.dumps(
        encoded,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=_json_default,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


class Phase1AcceptanceReceiptSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    application_build: str
    schema_revision: str
    acceptance_suite_version: str
    acceptance_run_id: str
    result_fingerprint: str
    restore_high_water_mark: int
    accepted_at: str
    fingerprint: str


class Phase1ReadinessSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    contract_version: Literal["phase1.activation.v1"] = "phase1.activation.v1"
    ready_for_phase_2: bool
    manifest_version: str
    import_run_id: str
    source_hashes: dict[str, str]
    active_profile_version: int
    readiness_generation: int
    authority_high_water_mark: int
    restore_generation: int
    blocker_codes: tuple[str, ...] = Field(default=())
    fingerprint: str


class SearchProfileSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    version_number: int
    payload: SearchProfilePayload
    active_profile_generation: int
    fingerprint: str


class Phase1ActivationInputs(BaseModel):
    model_config = ConfigDict(frozen=True)

    acceptance_receipt: Phase1AcceptanceReceiptSnapshot
    readiness: Phase1ReadinessSnapshot
    profile: SearchProfileSnapshot


class Phase1ResumeFactProjectionRequest(BaseModel):
    """A bounded request for approved facts, never free-form job instructions."""

    model_config = ConfigDict(frozen=True)

    purpose: Literal["tailored_resume"] = "tailored_resume"
    requirement_ids: tuple[str, ...] = Field(min_length=1, max_length=32)

    @field_validator("requirement_ids")
    @classmethod
    def validate_requirement_ids(cls, requirement_ids: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(requirement_ids)) != len(requirement_ids):
            raise ValueError("Requirement IDs must be unique.")
        if any(
            re.fullmatch(r"[a-z][a-z0-9_.-]{0,254}", requirement_id) is None
            for requirement_id in requirement_ids
        ):
            raise ValueError("Requirement IDs must be canonical identifiers.")
        return requirement_ids


class Phase1ResumeFactSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    requirement_id: str
    claim_id: str
    revision_id: str
    support_assertion_id: str
    safe_wording: str
    employer_key: str | None
    period_start: str | None
    period_end: str | None


class Phase1ResumeFactProjection(BaseModel):
    model_config = ConfigDict(frozen=True)

    contract_version: Literal["phase1.resume-fact-projection.v1"] = (
        "phase1.resume-fact-projection.v1"
    )
    requirement_ids: tuple[str, ...]
    facts: tuple[Phase1ResumeFactSnapshot, ...]
    profile_fingerprint: str
    profile_generation: int
    readiness_fingerprint: str
    readiness_generation: int
    authority_fingerprint: str
    authority_generation: int
    restore_generation: int
    fingerprint: str


_MATCHING_TAXONOMY: dict[str, frozenset[str]] = {
    "capability": frozenset(
        {
            "capability.applied_ai",
            "capability.cross_functional_leadership",
            "capability.data_analytics",
            "capability.lifecycle_management",
            "capability.partner_integration",
            "capability.platform_product",
            "capability.product_delivery",
            "capability.product_discovery",
            "capability.product_strategy",
            "capability.roadmap_prioritization",
            "capability.stakeholder_influence",
        }
    ),
    "responsibility": frozenset(
        {
            "responsibility.delivery_ownership",
            "responsibility.discovery_ownership",
            "responsibility.executive_influence",
            "responsibility.kpi_ownership",
            "responsibility.people_leadership",
            "responsibility.product_decisions",
            "responsibility.roadmap_ownership",
            "responsibility.technical_tradeoffs",
        }
    ),
    "domain": frozenset(
        {
            "domain.applied_ai",
            "domain.banking",
            "domain.billing",
            "domain.commerce",
            "domain.decision_support",
            "domain.ecommerce",
            "domain.fintech",
            "domain.fraud",
            "domain.fulfilment",
            "domain.home_buying",
            "domain.last_mile",
            "domain.lending",
            "domain.mortgage",
            "domain.omnichannel",
            "domain.payments",
            "domain.risk",
            "domain.subscriptions",
        }
    ),
    "technical_object": frozenset(
        {
            "technical_object.ai",
            "technical_object.analytics",
            "technical_object.api",
            "technical_object.data",
            "technical_object.integration",
            "technical_object.platform",
            "technical_object.system",
        }
    ),
    "outcome_scale": frozenset(
        {
            "outcome_scale.adoption",
            "outcome_scale.commercial",
            "outcome_scale.enterprise",
            "outcome_scale.kpi",
            "outcome_scale.operational_complexity",
            "outcome_scale.regulated",
        }
    ),
    "role_profile": frozenset(
        {
            "role_profile.applied_ai_product_manager",
            "role_profile.principal_product_manager_ic",
            "role_profile.senior_product_manager",
            "role_profile.technical_product_manager",
        }
    ),
}


class Phase1MatchingRequirementPredicate(BaseModel):
    """One public requirement expressed only through the frozen taxonomy."""

    model_config = ConfigDict(frozen=True)

    requirement_id: str
    component: Literal[
        "role",
        "domain",
        "responsibility",
        "outcome",
        "technical",
        "seniority",
        "evidence",
    ]
    modality: Literal["required", "material_responsibility", "preferred", "uncertain"]
    capability_ids: tuple[str, ...] = Field(default=(), max_length=8)
    responsibility_ids: tuple[str, ...] = Field(default=(), max_length=8)
    domain_ids: tuple[str, ...] = Field(default=(), max_length=8)
    technical_object_ids: tuple[str, ...] = Field(default=(), max_length=8)
    outcome_scale_ids: tuple[str, ...] = Field(default=(), max_length=8)
    role_profile_ids: tuple[str, ...] = Field(default=(), max_length=4)
    employer_constraint: Literal["any", "attributed"] = "any"
    period_constraint: Literal["any", "dated", "open_ended"] = "any"

    @field_validator("requirement_id")
    @classmethod
    def validate_public_requirement_id(cls, requirement_id: str) -> str:
        Phase1ResumeFactProjectionRequest.validate_requirement_ids((requirement_id,))
        if not requirement_id.startswith("job."):
            raise ValueError("Matching requirement IDs must be public job identifiers.")
        return requirement_id

    @field_validator(
        "capability_ids",
        "responsibility_ids",
        "domain_ids",
        "technical_object_ids",
        "outcome_scale_ids",
        "role_profile_ids",
    )
    @classmethod
    def validate_taxonomy_ids(
        cls, taxonomy_ids: tuple[str, ...], info: ValidationInfo
    ) -> tuple[str, ...]:
        if len(set(taxonomy_ids)) != len(taxonomy_ids):
            raise ValueError("Controlled taxonomy IDs must be unique.")
        field_name = str(info.field_name)
        taxonomy_name = field_name.removesuffix("_ids")
        allowed = _MATCHING_TAXONOMY[taxonomy_name]
        if any(taxonomy_id not in allowed for taxonomy_id in taxonomy_ids):
            raise ValueError("Only a known controlled taxonomy ID may be used.")
        return taxonomy_ids

    def taxonomy_ids(self) -> tuple[str, ...]:
        return (
            *self.capability_ids,
            *self.responsibility_ids,
            *self.domain_ids,
            *self.technical_object_ids,
            *self.outcome_scale_ids,
            *self.role_profile_ids,
        )

    @model_validator(mode="after")
    def require_taxonomy_predicate(self) -> "Phase1MatchingRequirementPredicate":
        if not self.taxonomy_ids():
            raise ValueError("A requirement must include at least one controlled taxonomy ID.")
        return self


class Phase1MatchingRequirementQuery(BaseModel):
    """A bounded job-level semantic query with no listing prose or fact keys."""

    model_config = ConfigDict(frozen=True)

    requirement_ids: tuple[str, ...] = Field(min_length=1, max_length=32)
    query_version: Literal["phase1.matching-query.v2"] = "phase1.matching-query.v2"
    job_revision_id: str = ""
    coverage_ledger_fingerprint: str = ""
    launch_session_fingerprint: str = ""
    requirements: tuple[Phase1MatchingRequirementPredicate, ...] = Field(
        default=(), max_length=32
    )

    @field_validator("requirement_ids")
    @classmethod
    def validate_requirement_ids(cls, requirement_ids: tuple[str, ...]) -> tuple[str, ...]:
        return Phase1ResumeFactProjectionRequest.validate_requirement_ids(requirement_ids)

    @model_validator(mode="after")
    def validate_semantic_bundle(self) -> "Phase1MatchingRequirementQuery":
        if not self.requirements:
            return self
        if tuple(item.requirement_id for item in self.requirements) != self.requirement_ids:
            raise ValueError(
                "Semantic requirements must exactly match the ordered requirement IDs."
            )
        for value in (
            self.coverage_ledger_fingerprint,
            self.launch_session_fingerprint,
        ):
            if re.fullmatch(r"[0-9a-f]{64}", value) is None:
                raise ValueError("Matching bundle fingerprints must be lowercase SHA-256 values.")
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,254}", self.job_revision_id) is None:
            raise ValueError("The job revision ID is invalid.")
        taxonomy_ids = {
            taxonomy_id
            for requirement in self.requirements
            for taxonomy_id in requirement.taxonomy_ids()
        }
        if len(taxonomy_ids) > 24:
            raise ValueError("A matching bundle may use at most 24 controlled taxonomy IDs.")
        return self


class Phase1MatchingManifestChoice(BaseModel):
    model_config = ConfigDict(frozen=True)

    claim_id: str
    revision_id: str
    support_assertion_id: str
    safe_wording_sha256: str

    @field_validator("safe_wording_sha256")
    @classmethod
    def validate_wording_hash(cls, value: str) -> str:
        if re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("A manifest wording hash must be lowercase SHA-256.")
        return value


class Phase1MatchingRelevanceEdge(BaseModel):
    model_config = ConfigDict(frozen=True)

    requirement_id: str
    claim_id: str
    matched_taxonomy_ids: tuple[str, ...]


class Phase1MatchingRetrievalManifest(BaseModel):
    """Immutable preflight metadata; deliberately contains no career wording."""

    model_config = ConfigDict(frozen=True)

    contract_version: Literal["phase1.matching-retrieval-manifest.v1"] = (
        "phase1.matching-retrieval-manifest.v1"
    )
    query: Phase1MatchingRequirementQuery
    query_fingerprint: str
    retrieval_policy_version: Literal["phase1.matching-retrieval.v1"] = (
        "phase1.matching-retrieval.v1"
    )
    choices: tuple[Phase1MatchingManifestChoice, ...]
    edges: tuple[Phase1MatchingRelevanceEdge, ...]
    candidate_universe_count: int = Field(ge=0)
    examined_count: int = Field(ge=0)
    omission_reason_counts: tuple[tuple[str, int], ...]
    complete: bool
    structural_state: Literal["complete", "incomplete"]
    semantic_state: Literal["complete", "unknown"]
    eligible_set_fingerprint: str
    profile_fingerprint: str
    profile_generation: int
    readiness_fingerprint: str
    readiness_generation: int
    authority_fingerprint: str
    authority_generation: int
    restore_generation: int
    disclosure_budget_epoch: int = Field(ge=1)
    disclosure_policy_generation: int = Field(ge=1)
    fingerprint: str


class Phase1DisclosurePayloadContext(BaseModel):
    """Typed Phase II digest context; contains metadata and never career wording."""

    model_config = ConfigDict(frozen=True)

    context_version: Literal["phase1.matching-disclosure-context.v1"] = (
        "phase1.matching-disclosure-context.v1"
    )
    packet_id: str = Field(min_length=1, max_length=160)
    attempt_id: str = Field(min_length=1, max_length=160)
    nonce: str = Field(min_length=1, max_length=160)
    phase2_authorization_id: str = Field(min_length=1, max_length=160)
    manifest_fingerprint: str
    job_revision_id: str = Field(min_length=1, max_length=255)
    selected_location_path: tuple[str, ...] = Field(min_length=1, max_length=8)
    coverage_ledger_fingerprint: str
    validated_requirements_fingerprint: str
    rubric_fingerprint: str
    retrieval_configuration_version: str = Field(min_length=1, max_length=120)
    interpreter_configuration_version: str = Field(min_length=1, max_length=120)
    response_schema_version: str = Field(min_length=1, max_length=120)
    phase1_profile_generation: int = Field(ge=0)
    phase1_readiness_generation: int = Field(ge=0)
    phase1_authority_generation: int = Field(ge=0)
    phase1_restore_generation: int = Field(ge=0)
    disclosure_budget_epoch: int = Field(ge=1)
    disclosure_policy_generation: int = Field(ge=1)
    phase2_activation_generation: int = Field(ge=0)
    phase2_restore_generation: int = Field(ge=0)
    recipient_mode: Literal["local_manual"] = "local_manual"
    issued_at: datetime
    expires_at: datetime
    allowed_relations: tuple[Literal["direct", "adjacent", "none"], ...] = Field(
        min_length=1, max_length=3
    )
    allowed_reason_codes: tuple[str, ...] = Field(min_length=1, max_length=16)

    @field_validator(
        "manifest_fingerprint",
        "coverage_ledger_fingerprint",
        "validated_requirements_fingerprint",
        "rubric_fingerprint",
    )
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("Disclosure fingerprints must be lowercase SHA-256 values.")
        return value

    @model_validator(mode="after")
    def validate_context(self) -> "Phase1DisclosurePayloadContext":
        if self.expires_at <= self.issued_at:
            raise ValueError("Disclosure expiry must follow its issue time.")
        if len(set(self.selected_location_path)) != len(self.selected_location_path):
            raise ValueError("The selected location path is invalid.")
        if len(set(self.allowed_relations)) != len(self.allowed_relations):
            raise ValueError("Allowed relations must be unique.")
        if len(set(self.allowed_reason_codes)) != len(self.allowed_reason_codes):
            raise ValueError("Allowed reason codes must be unique.")
        return self


class Phase1DisclosureAuthorizationRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    context: Phase1DisclosurePayloadContext
    logical_payload_digest: str

    @field_validator("logical_payload_digest")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        if re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("The logical payload digest must be lowercase SHA-256.")
        return value


DisclosureState = Literal[
    "authorized",
    "consuming",
    "validated_response",
    "expired",
    "denied",
    "failed",
    "indeterminate",
    "cancelled",
]


class Phase1FactDisclosureAuthorizationSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    authorization_id: str
    attempt_id: str
    nonce_sha256: str
    manifest_fingerprint: str
    logical_payload_digest: str
    disclosure_budget_epoch: int = Field(ge=1)
    disclosure_policy_generation: int = Field(ge=1)
    state: DisclosureState
    expires_at: datetime
    fingerprint: str


class Phase1WordingReleaseRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    authorization: Phase1FactDisclosureAuthorizationSnapshot
    attempt_id: str = Field(min_length=1, max_length=160)
    nonce: str = Field(min_length=1, max_length=160)


class Phase1DisclosureLifecycleRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    authorization_id: str = Field(min_length=1, max_length=160)
    logical_payload_digest: str
    state: Literal[
        "consuming",
        "validated_response",
        "expired",
        "denied",
        "failed",
        "indeterminate",
        "cancelled",
    ]
    reason_code: str = Field(default="", max_length=120)


class Phase1DisclosureLifecycleSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    authorization_id: str
    sequence: int = Field(ge=1)
    state: DisclosureState
    fingerprint: str


class Phase1MatchingReleasedChoice(BaseModel):
    model_config = ConfigDict(frozen=True)

    canonical_key: str
    claim_id: str
    revision_id: str
    support_assertion_id: str
    safe_wording: str
    safe_wording_sha256: str


class Phase1MatchingWordingRelease(BaseModel):
    model_config = ConfigDict(frozen=True)

    contract_version: Literal["phase1.matching-wording-release.v1"] = (
        "phase1.matching-wording-release.v1"
    )
    authorization_id: str
    logical_payload_digest: str
    manifest_fingerprint: str
    choices: tuple[Phase1MatchingReleasedChoice, ...]
    edges: tuple[Phase1MatchingRelevanceEdge, ...]
    fingerprint: str


class Phase1DisclosureEpochRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    reason: str = Field(min_length=1, max_length=500)
    confirmation: str = Field(min_length=1, max_length=80)


class Phase1DisclosureEpochSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    epoch_number: int = Field(ge=1)
    policy_generation: int = Field(ge=1)
    fingerprint: str


class Phase1MatchingFactSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    requirement_id: str
    claim_id: str
    revision_id: str
    support_assertion_id: str


class Phase1MatchingFactSetSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    contract_version: Literal["phase1.matching-fact-set.v1"] = "phase1.matching-fact-set.v1"
    requirement_ids: tuple[str, ...]
    facts: tuple[Phase1MatchingFactSnapshot, ...]
    complete: Literal[True] = True
    profile_fingerprint: str
    profile_generation: int
    readiness_fingerprint: str
    readiness_generation: int
    authority_fingerprint: str
    authority_generation: int
    restore_generation: int
    fingerprint: str


class Phase1ManualContentReviewRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    canonical_key: str
    category: Literal["career_fact", "resume_wording", "application_answer"]
    safe_wording: str = Field(min_length=1, max_length=2_000)

    @field_validator("canonical_key")
    @classmethod
    def validate_canonical_key(cls, canonical_key: str) -> str:
        if re.fullmatch(r"[a-z][a-z0-9_.-]{0,254}", canonical_key) is None:
            raise ValueError("The manual-content key must be a canonical identifier.")
        return canonical_key


class Phase1ManualContentReviewReceipt(BaseModel):
    model_config = ConfigDict(frozen=True)

    claim_id: str
    revision_id: str
    status: Literal["unresolved"]
    origin: Literal["user"]
