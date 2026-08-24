from datetime import UTC, datetime

import pytest

from job_search_cockpit.phase2.resume_safety import (
    ResumePreparationError,
    ResumePreparationService,
    VerifiedJobPreparationAuthorization,
)

FUTURE_EXPIRY = datetime(2026, 8, 25, tzinfo=UTC)


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
            return VerifiedJobPreparationAuthorization(
                job_id=job_id,
                job_revision_id="sanitized-revision-1",
                authorization_id="sanitized-authorization-1",
                eligibility="needs_clarification",
                expires_at=FUTURE_EXPIRY,
                activation_generation=1,
                unknown_mandatory_rule_codes=("notice_period",),
            )

    service = ResumePreparationService(UnknownMandatoryConditionPort())

    with pytest.raises(ResumePreparationError, match="unknown mandatory condition"):
        service.start(job_id="sanitized-job-1", resume_kind="tailored")


def test_failed_eligibility_stops_tailored_preparation() -> None:
    class IneligibleJobPort:
        def authorization_for_resume(self, job_id: str) -> VerifiedJobPreparationAuthorization:
            return VerifiedJobPreparationAuthorization(
                job_id=job_id,
                job_revision_id="sanitized-revision-1",
                authorization_id="sanitized-authorization-1",
                eligibility="ineligible",
                expires_at=FUTURE_EXPIRY,
                activation_generation=1,
            )

    service = ResumePreparationService(IneligibleJobPort())

    with pytest.raises(ResumePreparationError, match="not eligible"):
        service.start(job_id="sanitized-job-1", resume_kind="tailored")


def test_expired_authorization_stops_tailored_preparation() -> None:
    class ExpiredAuthorizationPort:
        def authorization_for_resume(self, job_id: str) -> VerifiedJobPreparationAuthorization:
            return VerifiedJobPreparationAuthorization(
                job_id=job_id,
                job_revision_id="sanitized-revision-1",
                authorization_id="sanitized-authorization-1",
                eligibility="eligible",
                expires_at=datetime(2026, 8, 24, 8, 59, tzinfo=UTC),
                activation_generation=1,
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
            return VerifiedJobPreparationAuthorization(
                job_id="sanitized-job-2",
                job_revision_id="sanitized-revision-1",
                authorization_id="sanitized-authorization-1",
                eligibility="eligible",
                expires_at=FUTURE_EXPIRY,
                activation_generation=1,
            )

    service = ResumePreparationService(MismatchedJobPort())

    with pytest.raises(ResumePreparationError, match="does not match"):
        service.start(job_id="sanitized-job-1", resume_kind="tailored")


def test_valid_authorization_requires_durable_preparation_metadata() -> None:
    class EligibleJobPort:
        def authorization_for_resume(self, job_id: str) -> VerifiedJobPreparationAuthorization:
            return VerifiedJobPreparationAuthorization(
                job_id=job_id,
                job_revision_id="sanitized-revision-1",
                authorization_id="sanitized-authorization-1",
                eligibility="eligible",
                expires_at=FUTURE_EXPIRY,
                activation_generation=1,
            )

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
            return VerifiedJobPreparationAuthorization(
                job_id=job_id,
                job_revision_id="sanitized-revision-1",
                authorization_id="sanitized-authorization-1",
                eligibility="eligible",
                expires_at=FUTURE_EXPIRY,
                activation_generation=1,
            )

        def revalidate_resume_authorization(
            self, expected: VerifiedJobPreparationAuthorization
        ) -> VerifiedJobPreparationAuthorization:
            return VerifiedJobPreparationAuthorization(
                job_id=expected.job_id,
                job_revision_id="sanitized-revision-2",
                authorization_id=expected.authorization_id,
                eligibility=expected.eligibility,
                expires_at=expected.expires_at,
                activation_generation=expected.activation_generation,
            )

    service = ResumePreparationService(ChangedAuthorizationPort())

    with pytest.raises(ResumePreparationError, match="changed"):
        service.start(job_id="sanitized-job-1", resume_kind="tailored")
