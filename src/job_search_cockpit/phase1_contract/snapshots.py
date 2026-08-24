import json
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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
