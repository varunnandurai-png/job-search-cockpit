from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol, TypeVar

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
        operation: Callable[[DatabaseSession], T],
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
        sensitivity: object,
        expected_version: int,
        reason: str = "",
    ) -> object: ...

    def bulk_approve_low_risk(self, items: Sequence[object]) -> object: ...


class ReadinessServicePort(Protocol):
    def report(self) -> object: ...


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


@dataclass(slots=True)
class PreparedVault:
    instance_lock: AppInstanceLockPort
    coordinator: MutationCoordinatorPort
    engine: object
    services: ServiceBundle
