from dataclasses import dataclass

from job_search_cockpit.phase2.assessment_types import (
    EligibilityState,
    GateResult,
    LocationEligibilityPath,
)
from job_search_cockpit.search_profile.catalog import SearchProfilePayload


@dataclass(frozen=True, slots=True)
class LocationGateInput:
    location_id: str
    result: GateResult

    def __post_init__(self) -> None:
        if not self.location_id.strip():
            raise ValueError("location ID is required")


@dataclass(frozen=True, slots=True)
class JobGateInput:
    employer_name: str

    def __post_init__(self) -> None:
        if not self.employer_name.strip():
            raise ValueError("employer name is required")


@dataclass(frozen=True, slots=True)
class LocationPathResult:
    state: GateResult
    passing_location_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EligibilityAssessment:
    """Fail-closed aggregation of global gates and independent location paths."""

    global_gate_results: tuple[GateResult, ...]
    location_paths: tuple[LocationEligibilityPath, ...]

    def __post_init__(self) -> None:
        if not self.global_gate_results or not self.location_paths:
            raise ValueError("global gates and location paths are required")

    @property
    def state(self) -> EligibilityState:
        if GateResult.FAIL in self.global_gate_results:
            return EligibilityState.INELIGIBLE
        if not any(path.result is GateResult.PASS for path in self.location_paths):
            return (
                EligibilityState.NEEDS_CLARIFICATION
                if GateResult.UNKNOWN in self.global_gate_results
                or any(path.result is GateResult.UNKNOWN for path in self.location_paths)
                else EligibilityState.INELIGIBLE
            )
        if GateResult.UNKNOWN in self.global_gate_results:
            return EligibilityState.NEEDS_CLARIFICATION
        return EligibilityState.ELIGIBLE

    @property
    def shortlist_allowed(self) -> bool:
        return self.state is EligibilityState.ELIGIBLE


def aggregate_location_paths(paths: tuple[LocationGateInput, ...]) -> LocationPathResult:
    if not paths:
        raise ValueError("at least one location path is required")
    passing = tuple(path.location_id for path in paths if path.result is GateResult.PASS)
    if passing:
        return LocationPathResult(GateResult.PASS, passing)
    if any(path.result is GateResult.UNKNOWN for path in paths):
        return LocationPathResult(GateResult.UNKNOWN, ())
    return LocationPathResult(GateResult.FAIL, ())


def evaluate_excluded_employer(
    profile: SearchProfilePayload, job: JobGateInput
) -> GateResult:
    normalized_employer = "".join(job.employer_name.casefold().split())
    for excluded_employer in profile.excluded_employers:
        if "".join(excluded_employer.casefold().split()) in normalized_employer:
            return GateResult.FAIL
    return GateResult.PASS
