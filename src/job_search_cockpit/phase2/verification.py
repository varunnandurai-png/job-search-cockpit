from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from job_search_cockpit.phase1_contract.snapshots import (
    Phase1ActivationInputs,
    canonical_fingerprint,
)
from job_search_cockpit.phase2.activation import Phase2ActivationService
from job_search_cockpit.phase2.config import Phase2Settings
from job_search_cockpit.phase2.models import (
    Phase2JobRecord,
    Phase2JobRevision,
    Phase2JobVerification,
    Phase2ResumeRequirementLedger,
    Phase2SourceListingObservation,
)
from job_search_cockpit.phase2.mutation import Phase2MutationCoordinator
from job_search_cockpit.phase2.resume_safety import (
    ResumePreparationError,
    VerifiedJobPreparationAuthorization,
)
from job_search_cockpit.phase2.types import Phase2Action, Phase2ActivationUnavailable
from job_search_cockpit.ports import Phase1MatchingPort

_CONFIRMATION = "VERIFY JOB FOR PHASE II PREPARATION"
_AUTHORIZATION_TTL = timedelta(minutes=15)


@dataclass(frozen=True, slots=True)
class VerifyCandidateCommand:
    job_revision_id: str
    selected_location_path: str
    actor: str
    reason: str
    confirmation: str
    eligibility: Literal["eligible", "ineligible", "needs_clarification"]
    unknown_mandatory_rule_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.job_revision_id,
                self.selected_location_path,
                self.actor,
                self.reason,
            )
        ):
            raise ValueError("A job revision, location path, actor, and reason are required.")
        if self.confirmation != _CONFIRMATION:
            raise ValueError("Type the exact verification confirmation.")
        if any(not code.strip() for code in self.unknown_mandatory_rule_codes):
            raise ValueError("Mandatory-rule codes must be non-empty.")


class VerifiedJobAuthorizationService:
    def __init__(
        self,
        phase1_port: Phase1MatchingPort,
        activation_service: Phase2ActivationService,
        coordinator: Phase2MutationCoordinator,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._phase1_port = phase1_port
        self._activation_service = activation_service
        self._coordinator = coordinator
        self._now = now or (lambda: datetime.now(UTC))

    def verify(self, command: VerifyCandidateCommand) -> VerifiedJobPreparationAuthorization:
        self._assert_assessed(command)
        self._activation_service.revalidate_before(Phase2Action.VERIFICATION)
        expected_phase1 = self._phase1_port.activation_inputs()
        self._assert_location_path(command.selected_location_path, expected_phase1)

        def record(session: Session) -> VerifiedJobPreparationAuthorization:
            view = self._activation_service.revalidate_before(Phase2Action.VERIFICATION)
            self._phase1_port.revalidate_activation_inputs(expected_phase1)
            revision = session.get(Phase2JobRevision, command.job_revision_id)
            if revision is None:
                raise ResumePreparationError("The job revision is unavailable for verification.")
            observation = session.get(
                Phase2SourceListingObservation, revision.source_observation_id
            )
            if observation is None or self._is_stale(session, revision):
                raise ResumePreparationError("The job revision is stale and cannot be verified.")
            job = session.get(Phase2JobRecord, revision.job_record_id)
            if job is None:
                raise ResumePreparationError("The job record is unavailable for verification.")
            authorization_id = str(uuid4())
            authorization_nonce = str(uuid4())
            selected_location_path_fingerprint = canonical_fingerprint(
                {"location_path": command.selected_location_path.strip()}
            )
            verification = Phase2JobVerification(
                id=str(uuid4()),
                authorization_id=authorization_id,
                authorization_nonce=authorization_nonce,
                job_revision_id=revision.id,
                selected_location_path_fingerprint=selected_location_path_fingerprint,
                source_observation_fingerprint=observation.content_fingerprint,
                **_phase1_fields(expected_phase1),
                phase2_activation_generation=view.activation_generation,
                phase2_restore_generation=view.restore_generation,
                expires_at=self._now() + _AUTHORIZATION_TTL,
            )
            session.add(verification)
            session.flush()
            return _authorization(job.id, verification)

        return self._coordinator.run(record, "verify_phase2_job", actor=command.actor)

    @staticmethod
    def _assert_assessed(command: VerifyCandidateCommand) -> None:
        if command.eligibility != "eligible":
            raise ResumePreparationError("The job eligibility is unresolved.")
        if command.unknown_mandatory_rule_codes:
            raise ResumePreparationError("The job has an unknown mandatory condition.")

    @staticmethod
    def _assert_location_path(location_path: str, inputs: Phase1ActivationInputs) -> None:
        if location_path.strip() not in inputs.profile.payload.locations:
            raise ResumePreparationError("The selected location path is not eligible.")

    @staticmethod
    def _is_stale(session: Session, revision: Phase2JobRevision) -> bool:
        current = session.scalar(
            select(Phase2JobRevision.id)
            .where(Phase2JobRevision.job_record_id == revision.job_record_id)
            .order_by(Phase2JobRevision.created_at.desc(), Phase2JobRevision.id.desc())
        )
        return current != revision.id


class CatalogVerifiedJobPreparationPort:
    def __init__(
        self,
        phase1_port: Phase1MatchingPort | None = None,
        activation_service: Phase2ActivationService | None = None,
        coordinator: Phase2MutationCoordinator | None = None,
    ) -> None:
        self._phase1_port = phase1_port
        self._activation_service = activation_service
        self._coordinator = coordinator

    @classmethod
    def unavailable(cls, _settings: Phase2Settings) -> CatalogVerifiedJobPreparationPort:
        return cls()

    def authorization_for_resume(self, job_id: str) -> VerifiedJobPreparationAuthorization:
        verification, job, revision, ledger = self._current_verification(job_id)
        return self._revalidate(job, revision, verification, ledger)

    def revalidate_resume_authorization(
        self, expected: VerifiedJobPreparationAuthorization
    ) -> VerifiedJobPreparationAuthorization:
        verification, job, revision, ledger = self._current_verification(expected.job_id)
        authorization = self._revalidate(job, revision, verification, ledger)
        if authorization != expected:
            raise ResumePreparationError("verified job readiness is unavailable")
        return authorization

    def _current_verification(
        self, job_id: str
    ) -> tuple[
        Phase2JobVerification,
        Phase2JobRecord,
        Phase2JobRevision,
        Phase2ResumeRequirementLedger | None,
    ]:
        if self._coordinator is None:
            raise ResumePreparationError("verified job readiness is unavailable")
        with self._coordinator._session_factory() as session:
            job = session.get(Phase2JobRecord, job_id)
            if job is None:
                raise ResumePreparationError("verified job readiness is unavailable")
            verification = session.scalar(
                select(Phase2JobVerification)
                .join(
                    Phase2JobRevision,
                    Phase2JobVerification.job_revision_id == Phase2JobRevision.id,
                )
                .where(Phase2JobRevision.job_record_id == job.id)
                .order_by(Phase2JobVerification.created_at.desc(), Phase2JobVerification.id.desc())
            )
            if verification is None:
                raise ResumePreparationError("verified job readiness is unavailable")
            ledger = session.scalar(
                select(Phase2ResumeRequirementLedger)
                .where(
                    Phase2ResumeRequirementLedger.job_id == job.id,
                    Phase2ResumeRequirementLedger.job_revision_id == verification.job_revision_id,
                )
                .order_by(Phase2ResumeRequirementLedger.created_at.desc())
            )
            revision = session.get(Phase2JobRevision, verification.job_revision_id)
            if revision is None:
                raise ResumePreparationError("verified job readiness is unavailable")
            return verification, job, revision, ledger

    def _revalidate(
        self,
        job: Phase2JobRecord,
        revision: Phase2JobRevision,
        verification: Phase2JobVerification,
        ledger: Phase2ResumeRequirementLedger | None,
    ) -> VerifiedJobPreparationAuthorization:
        if self._phase1_port is None or self._activation_service is None:
            raise ResumePreparationError("verified job readiness is unavailable")
        if _as_utc(verification.expires_at) <= datetime.now(UTC):
            raise ResumePreparationError("verified job readiness is unavailable")
        try:
            view = self._activation_service.revalidate_before(Phase2Action.VERIFICATION)
            inputs = self._phase1_port.activation_inputs()
        except Phase2ActivationUnavailable as error:
            raise ResumePreparationError("verified job readiness is unavailable") from error
        if _phase1_fields(inputs) != {
            "phase1_profile_fingerprint": verification.phase1_profile_fingerprint,
            "phase1_profile_generation": verification.phase1_profile_generation,
            "phase1_readiness_fingerprint": verification.phase1_readiness_fingerprint,
            "phase1_readiness_generation": verification.phase1_readiness_generation,
            "phase1_authority_fingerprint": verification.phase1_authority_fingerprint,
            "phase1_authority_generation": verification.phase1_authority_generation,
            "phase1_restore_generation": verification.phase1_restore_generation,
        } or (
            view.activation_generation != verification.phase2_activation_generation
            or view.restore_generation != verification.phase2_restore_generation
        ):
            raise ResumePreparationError("verified job readiness is unavailable")
        return _authorization(job.id, verification, revision, ledger)


def _phase1_fields(inputs: Phase1ActivationInputs) -> dict[str, object]:
    return {
        "phase1_profile_fingerprint": inputs.profile.fingerprint,
        "phase1_profile_generation": inputs.profile.active_profile_generation,
        "phase1_readiness_fingerprint": inputs.readiness.fingerprint,
        "phase1_readiness_generation": inputs.readiness.readiness_generation,
        "phase1_authority_fingerprint": inputs.acceptance_receipt.fingerprint,
        "phase1_authority_generation": inputs.readiness.authority_high_water_mark,
        "phase1_restore_generation": inputs.readiness.restore_generation,
    }


def _authorization(
    job_id: str,
    verification: Phase2JobVerification,
    revision: Phase2JobRevision | None = None,
    ledger: Phase2ResumeRequirementLedger | None = None,
) -> VerifiedJobPreparationAuthorization:
    return VerifiedJobPreparationAuthorization(
        job_id=job_id,
        job_revision_id=verification.job_revision_id,
        selected_location_path_fingerprint=verification.selected_location_path_fingerprint,
        authorization_id=verification.authorization_id,
        authorization_nonce=verification.authorization_nonce,
        eligibility="eligible",
        expires_at=_as_utc(verification.expires_at),
        phase1_profile_fingerprint=verification.phase1_profile_fingerprint,
        phase1_profile_generation=verification.phase1_profile_generation,
        phase1_readiness_fingerprint=verification.phase1_readiness_fingerprint,
        phase1_readiness_generation=verification.phase1_readiness_generation,
        phase1_authority_fingerprint=verification.phase1_authority_fingerprint,
        phase1_authority_generation=verification.phase1_authority_generation,
        phase1_restore_generation=verification.phase1_restore_generation,
        phase2_activation_generation=verification.phase2_activation_generation,
        phase2_restore_generation=verification.phase2_restore_generation,
        requirement_ids=(
            tuple(str(item) for item in ledger.requirement_ids_json) if ledger else ()
        ),
        requirement_ledger_fingerprint=(
            ledger.requirement_ledger_fingerprint if ledger else ""
        ),
        company_name=(revision.employer_name if revision is not None else ""),
        role_name=(revision.title if revision is not None else ""),
    )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


__all__ = [
    "CatalogVerifiedJobPreparationPort",
    "VerifiedJobAuthorizationService",
    "VerifyCandidateCommand",
]
