import json
import re
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class Phase1MatchingRequirementQuery(BaseModel):
    """Bounded opaque requirement IDs for Phase II matching only."""

    model_config = ConfigDict(frozen=True)

    requirement_ids: tuple[str, ...] = Field(min_length=1, max_length=32)

    @field_validator("requirement_ids")
    @classmethod
    def validate_requirement_ids(cls, requirement_ids: tuple[str, ...]) -> tuple[str, ...]:
        return Phase1ResumeFactProjectionRequest.validate_requirement_ids(requirement_ids)


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
