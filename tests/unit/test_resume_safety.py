from dataclasses import replace
from datetime import UTC, datetime

import pytest

from job_search_cockpit.phase2.resume_safety import (
    ResumePreparationError,
    ResumePreparationService,
    VerifiedJobPreparationAuthorization,
)

FUTURE_EXPIRY = datetime(2099, 1, 1, tzinfo=UTC)


def _authorization(**changes: object) -> VerifiedJobPreparationAuthorization:
    values: dict[str, object] = {
        "job_id": "sanitized-job-1",
        "job_revision_id": "sanitized-revision-1",
        "selected_location_path_fingerprint": "a" * 64,
        "authorization_id": "sanitized-authorization-1",
        "authorization_nonce": "sanitized-nonce-1",
        "eligibility": "eligible",
        "expires_at": FUTURE_EXPIRY,
        "phase1_profile_fingerprint": "b" * 64,
        "phase1_profile_generation": 3,
        "phase1_readiness_fingerprint": "c" * 64,
        "phase1_readiness_generation": 5,
        "phase1_authority_fingerprint": "d" * 64,
        "phase1_authority_generation": 7,
        "phase1_restore_generation": 11,
        "phase2_activation_generation": 13,
        "phase2_restore_generation": 17,
    }
    values.update(changes)
    return VerifiedJobPreparationAuthorization(**values)


class TrackingPreparationPort:
    def __init__(self) -> None:
        self.requested_job_ids: list[str] = []

    def authorization_for_resume(self, job_id: str) -> object:
        self.requested_job_ids.append(job_id)
        raise AssertionError("A generic résumé must not request authorization.")


def test_generic_resume_stops_before_requesting_verified_job_authorization() -> None:
    port = TrackingPreparationPort()
    service = ResumePreparationService(port)

    with pytest.raises(ResumePreparationError, match="generic résumé"):
        service.start(job_id="sanitized-job-1", resume_kind="generic")

    assert port.requested_job_ids == []


def test_unknown_mandatory_condition_stops_tailored_preparation() -> None:
    class UnknownMandatoryConditionPort:
        def authorization_for_resume(self, job_id: str) -> VerifiedJobPreparationAuthorization:
            return _authorization(
                job_id=job_id,
                eligibility="needs_clarification",
                unknown_mandatory_rule_codes=("notice_period",),
            )

    service = ResumePreparationService(UnknownMandatoryConditionPort())

    with pytest.raises(ResumePreparationError, match="unknown mandatory condition"):
        service.start(job_id="sanitized-job-1", resume_kind="tailored")


def test_failed_eligibility_stops_tailored_preparation() -> None:
    class IneligibleJobPort:
        def authorization_for_resume(self, job_id: str) -> VerifiedJobPreparationAuthorization:
            return _authorization(
                job_id=job_id,
                eligibility="ineligible",
            )

    service = ResumePreparationService(IneligibleJobPort())

    with pytest.raises(ResumePreparationError, match="not eligible"):
        service.start(job_id="sanitized-job-1", resume_kind="tailored")


def test_expired_authorization_stops_tailored_preparation() -> None:
    class ExpiredAuthorizationPort:
        def authorization_for_resume(self, job_id: str) -> VerifiedJobPreparationAuthorization:
            return _authorization(
                job_id=job_id,
                expires_at=datetime(2026, 8, 24, 8, 59, tzinfo=UTC),
            )

    service = ResumePreparationService(
        ExpiredAuthorizationPort(),
        now=lambda: datetime(2026, 8, 24, 9, 0, tzinfo=UTC),
    )

    with pytest.raises(ResumePreparationError, match="expired"):
        service.start(job_id="sanitized-job-1", resume_kind="tailored")


def test_authorization_for_another_job_stops_tailored_preparation() -> None:
    class MismatchedJobPort:
        def authorization_for_resume(self, job_id: str) -> VerifiedJobPreparationAuthorization:
            return _authorization(
                job_id="sanitized-job-2",
            )

    service = ResumePreparationService(MismatchedJobPort())

    with pytest.raises(ResumePreparationError, match="does not match"):
        service.start(job_id="sanitized-job-1", resume_kind="tailored")


def test_valid_authorization_requires_durable_preparation_metadata() -> None:
    class EligibleJobPort:
        def authorization_for_resume(self, job_id: str) -> VerifiedJobPreparationAuthorization:
            return _authorization(job_id=job_id)

        def revalidate_resume_authorization(
            self, expected: VerifiedJobPreparationAuthorization
        ) -> VerifiedJobPreparationAuthorization:
            return expected

    service = ResumePreparationService(EligibleJobPort())

    with pytest.raises(ResumePreparationError, match=r"Durable.*unavailable"):
        service.start(job_id="sanitized-job-1", resume_kind="tailored")


def test_changed_authorization_stops_before_durable_preparation_metadata() -> None:
    class ChangedAuthorizationPort:
        def authorization_for_resume(self, job_id: str) -> VerifiedJobPreparationAuthorization:
            return _authorization(job_id=job_id)

        def revalidate_resume_authorization(
            self, expected: VerifiedJobPreparationAuthorization
        ) -> VerifiedJobPreparationAuthorization:
            return replace(expected, phase1_profile_fingerprint="e" * 64)

    service = ResumePreparationService(ChangedAuthorizationPort())

    with pytest.raises(ResumePreparationError, match="changed"):
        service.start(job_id="sanitized-job-1", resume_kind="tailored")
