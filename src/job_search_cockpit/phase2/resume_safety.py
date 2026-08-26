from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from re import fullmatch
from typing import Literal, Protocol
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from job_search_cockpit.phase2.models import Phase2ResumePreparationAttempt
from job_search_cockpit.phase2.mutation import Phase2MutationCoordinator


class ResumePreparationError(ValueError):
    """Raised when résumé preparation cannot proceed safely."""


@dataclass(frozen=True, slots=True)
class VerifiedJobPreparationAuthorization:
    job_id: str
    job_revision_id: str
    selected_location_path_fingerprint: str
    authorization_id: str
    authorization_nonce: str
    eligibility: Literal["eligible", "ineligible", "needs_clarification"]
    expires_at: datetime
    phase1_profile_fingerprint: str
    phase1_profile_generation: int
    phase1_readiness_fingerprint: str
    phase1_readiness_generation: int
    phase1_authority_fingerprint: str
    phase1_authority_generation: int
    phase1_restore_generation: int
    phase2_activation_generation: int
    phase2_restore_generation: int
    requirement_ids: tuple[str, ...] = ()
    requirement_ledger_fingerprint: str = ""
    company_name: str = ""
    role_name: str = ""
    unknown_mandatory_rule_codes: tuple[str, ...] = ()


class VerifiedJobPreparationPort(Protocol):
    def authorization_for_resume(self, job_id: str) -> VerifiedJobPreparationAuthorization: ...

    def revalidate_resume_authorization(
        self, expected: VerifiedJobPreparationAuthorization
    ) -> VerifiedJobPreparationAuthorization: ...


class VerifiedJobReadinessUnavailable:
    """Fail closed until a future discovery phase issues verified job readiness."""

    def authorization_for_resume(self, job_id: str) -> VerifiedJobPreparationAuthorization:
        del job_id
        raise ResumePreparationError("verified job readiness is unavailable")

    def revalidate_resume_authorization(
        self, expected: VerifiedJobPreparationAuthorization
    ) -> VerifiedJobPreparationAuthorization:
        del expected
        raise ResumePreparationError("verified job readiness is unavailable")


def assert_phase3_requirement_ledger(
    authorization: VerifiedJobPreparationAuthorization,
) -> tuple[str, ...]:
    requirement_ids = authorization.requirement_ids
    if not requirement_ids or not authorization.requirement_ledger_fingerprint:
        raise ResumePreparationError("The verified job requirement ledger is unavailable.")
    if len(requirement_ids) > 32 or len(set(requirement_ids)) != len(requirement_ids):
        raise ResumePreparationError("The verified job requirement ledger is invalid.")
    if any(
        fullmatch(r"[a-z][a-z0-9_.-]{0,254}", requirement_id) is None
        for requirement_id in requirement_ids
    ):
        raise ResumePreparationError("The verified job requirement ledger is invalid.")
    if len(authorization.requirement_ledger_fingerprint) != 64:
        raise ResumePreparationError("The verified job requirement ledger is invalid.")
    return requirement_ids

@dataclass(frozen=True, slots=True)
class ResumePreparationAttempt:
    id: str
    job_id: str
    job_revision_id: str
    authorization_id: str
    phase2_activation_generation: int
    authorization: VerifiedJobPreparationAuthorization


class ResumePreparationAttemptStore:
    def __init__(self, coordinator: Phase2MutationCoordinator) -> None:
        self._coordinator = coordinator

    def record(
        self, authorization: VerifiedJobPreparationAuthorization
    ) -> ResumePreparationAttempt:
        def insert(session: Session) -> ResumePreparationAttempt:
            attempt = Phase2ResumePreparationAttempt(
                id=str(uuid4()),
                job_id=authorization.job_id,
                job_revision_id=authorization.job_revision_id,
                selected_location_path_fingerprint=authorization.selected_location_path_fingerprint,
                authorization_id=authorization.authorization_id,
                authorization_nonce=authorization.authorization_nonce,
                authorization_expires_at=authorization.expires_at,
                phase1_profile_fingerprint=authorization.phase1_profile_fingerprint,
                phase1_profile_generation=authorization.phase1_profile_generation,
                phase1_readiness_fingerprint=authorization.phase1_readiness_fingerprint,
                phase1_readiness_generation=authorization.phase1_readiness_generation,
                phase1_authority_fingerprint=authorization.phase1_authority_fingerprint,
                phase1_authority_generation=authorization.phase1_authority_generation,
                phase1_restore_generation=authorization.phase1_restore_generation,
                phase2_activation_generation=authorization.phase2_activation_generation,
                phase2_restore_generation=authorization.phase2_restore_generation,
            )
            session.add(attempt)
            session.flush()
            if attempt.phase2_activation_generation is None:
                raise ResumePreparationError(
                    "Durable résumé preparation metadata is incomplete."
                )
            return ResumePreparationAttempt(
                id=attempt.id,
                job_id=attempt.job_id,
                job_revision_id=attempt.job_revision_id,
                authorization_id=attempt.authorization_id,
                phase2_activation_generation=attempt.phase2_activation_generation,
                authorization=authorization,
            )

        try:
            return self._coordinator.run(insert, "record_resume_preparation_attempt")
        except IntegrityError as error:
            raise ResumePreparationError(
                "The verified job authorization has already been used."
            ) from error


class ResumePreparationService:
    def __init__(
        self,
        preparation_port: VerifiedJobPreparationPort,
        attempt_store: ResumePreparationAttemptStore | None = None,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._preparation_port = preparation_port
        self._attempt_store = attempt_store
        self._now = now or (lambda: datetime.now(UTC))

    def start(
        self, *, job_id: str, resume_kind: str
    ) -> ResumePreparationAttempt:
        if resume_kind == "generic":
            raise ResumePreparationError(
                "A generic résumé cannot be used; prepare a tailored résumé or stop."
            )
        if resume_kind != "tailored":
            raise ResumePreparationError("Choose a tailored résumé or stop.")
        authorization = self._preparation_port.authorization_for_resume(job_id)
        if authorization.job_id != job_id:
            raise ResumePreparationError("The verified job authorization does not match this job.")
        self._validate_binding(authorization)
        if authorization.expires_at <= self._now():
            raise ResumePreparationError("The verified job authorization has expired.")
        if authorization.unknown_mandatory_rule_codes:
            raise ResumePreparationError("The job has an unknown mandatory condition.")
        if authorization.eligibility != "eligible":
            raise ResumePreparationError("The job is not eligible for tailored résumé preparation.")
        revalidated = self._preparation_port.revalidate_resume_authorization(authorization)
        if revalidated != authorization:
            raise ResumePreparationError("The verified job authorization changed.")
        if self._attempt_store is None:
            raise ResumePreparationError("Durable résumé preparation metadata is unavailable.")
        return self._attempt_store.record(revalidated)

    @staticmethod
    def _validate_binding(authorization: VerifiedJobPreparationAuthorization) -> None:
        fingerprints = (
            authorization.selected_location_path_fingerprint,
            authorization.phase1_profile_fingerprint,
            authorization.phase1_readiness_fingerprint,
            authorization.phase1_authority_fingerprint,
        )
        if any(len(fingerprint) != 64 for fingerprint in fingerprints):
            raise ResumePreparationError("The verified job authorization binding is incomplete.")
        if not authorization.authorization_nonce.strip():
            raise ResumePreparationError("The verified job authorization binding is incomplete.")
        generations = (
            authorization.phase1_profile_generation,
            authorization.phase1_readiness_generation,
            authorization.phase1_authority_generation,
            authorization.phase1_restore_generation,
            authorization.phase2_activation_generation,
            authorization.phase2_restore_generation,
        )
        if any(generation < 0 for generation in generations):
            raise ResumePreparationError("The verified job authorization binding is incomplete.")
