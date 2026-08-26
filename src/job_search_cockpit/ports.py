from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Protocol, TypeVar

from sqlalchemy.orm import Session

from job_search_cockpit.phase1_contract.snapshots import (
    Phase1ActivationInputs,
    Phase1ManualContentReviewReceipt,
    Phase1ManualContentReviewRequest,
    Phase1MatchingFactSetSnapshot,
    Phase1MatchingRequirementQuery,
    Phase1ResumeFactProjection,
    Phase1ResumeFactProjectionRequest,
)

if TYPE_CHECKING:
    from job_search_cockpit.facts.review import BulkReviewItem
    from job_search_cockpit.facts.types import Sensitivity

T = TypeVar("T")


class Clock(Protocol):
    def now(self) -> datetime: ...


class MonotonicClock(Protocol):
    def now(self) -> float: ...


class DatabaseSession(Protocol):
    def add(self, instance: object) -> None: ...

    def flush(self) -> None: ...

    def execute(self, statement: object, params: object | None = None) -> Any: ...

    def close(self) -> None: ...


class MutationCoordinatorPort(Protocol):
    def run(
        self,
        operation: Callable[[Session], T],
        reason: str,
        expected_version: int | None,
    ) -> T: ...

    def restore(self, backup_id: str, actor: str, reason: str) -> object: ...


class ImportServicePort(Protocol):
    def preview(self, session_id: str, now: datetime) -> object: ...

    def apply(self, preview_id: str, session_id: str, now: datetime) -> object: ...


class ReviewServicePort(Protocol):
    def approve(
        self,
        claim_id: str,
        revision_id: str,
        expected_version: int,
        reason: str = "",
    ) -> object: ...

    def correct(
        self,
        claim_id: str,
        value: dict[str, object],
        display_value: str,
        employer_key: str | None,
        period_start: date | None,
        period_end: date | None,
        expected_version: int,
        reason: str,
    ) -> object: ...

    def reject(self, claim_id: str, expected_version: int, reason: str) -> object: ...

    def set_sensitivity(
        self,
        claim_id: str,
        sensitivity: Sensitivity,
        expected_version: int,
        reason: str = "",
    ) -> object: ...

    def bulk_approve_low_risk(self, items: Sequence[BulkReviewItem]) -> object: ...


class ReadinessServicePort(Protocol):
    def report(self) -> object: ...


class Phase1MatchingPort(Protocol):
    def activation_inputs(self) -> Phase1ActivationInputs: ...

    def revalidate_activation_inputs(
        self, expected: Phase1ActivationInputs
    ) -> Phase1ActivationInputs: ...

    def resume_fact_projection(
        self, request: Phase1ResumeFactProjectionRequest
    ) -> Phase1ResumeFactProjection: ...

    def revalidate_resume_fact_projection(
        self, expected: Phase1ResumeFactProjection
    ) -> Phase1ResumeFactProjection: ...

    def matching_fact_set(
        self, query: Phase1MatchingRequirementQuery
    ) -> Phase1MatchingFactSetSnapshot: ...

    def revalidate_matching_fact_set(
        self, expected: Phase1MatchingFactSetSnapshot
    ) -> Phase1MatchingFactSetSnapshot: ...

    def request_manual_content_review(
        self, request: Phase1ManualContentReviewRequest
    ) -> Phase1ManualContentReviewReceipt: ...


class AppInstanceLockPort(Protocol):
    def release(self) -> None: ...


@dataclass(slots=True)
class ServiceBundle:
    import_service: ImportServicePort
    review_service: ReviewServicePort
    readiness_service: ReadinessServicePort
    search_profile_service: object | None = None
    audit_service: object | None = None
    permission_service: object | None = None
    named_use_service: object | None = None
    phase1_contract_service: object | None = None
    phase1_matching_port: Phase1MatchingPort | None = None
    phase2_activation_service: object | None = None


@dataclass(slots=True)
class PreparedVault:
    instance_lock: AppInstanceLockPort
    coordinator: MutationCoordinatorPort
    engine: object
    services: ServiceBundle
    phase2_runtime: object | None = None
