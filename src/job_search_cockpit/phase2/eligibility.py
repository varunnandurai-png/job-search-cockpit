from dataclasses import dataclass

from job_search_cockpit.phase2.assessment_types import GateResult


@dataclass(frozen=True, slots=True)
class LocationGateInput:
    location_id: str
    result: GateResult

    def __post_init__(self) -> None:
        if not self.location_id.strip():
            raise ValueError("location ID is required")


@dataclass(frozen=True, slots=True)
class LocationPathResult:
    state: GateResult
    passing_location_ids: tuple[str, ...]


def aggregate_location_paths(paths: tuple[LocationGateInput, ...]) -> LocationPathResult:
    if not paths:
        raise ValueError("at least one location path is required")
    passing = tuple(path.location_id for path in paths if path.result is GateResult.PASS)
    if passing:
        return LocationPathResult(GateResult.PASS, passing)
    if any(path.result is GateResult.UNKNOWN for path in paths):
        return LocationPathResult(GateResult.UNKNOWN, ())
    return LocationPathResult(GateResult.FAIL, ())
