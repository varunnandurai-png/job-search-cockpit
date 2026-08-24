from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from job_search_cockpit.phase2.config import Phase2Settings
from job_search_cockpit.phase2.database import create_phase2_engine, upgrade_phase2_database
from job_search_cockpit.phase2.models import Phase2ResumePreparationAttempt
from job_search_cockpit.phase2.mutation import Phase2InstanceLock, Phase2MutationCoordinator
from job_search_cockpit.phase2.resume_safety import (
    ResumePreparationAttemptStore,
    ResumePreparationService,
    VerifiedJobPreparationAuthorization,
)


@contextmanager
def _coordinator(settings: Phase2Settings) -> Iterator[Phase2MutationCoordinator]:
    upgrade_phase2_database(f"sqlite:///{settings.database_path}")
    engine = create_phase2_engine(settings)
    lock = Phase2InstanceLock.acquire(settings)
    coordinator = Phase2MutationCoordinator(settings, engine, lock)
    try:
        yield coordinator
    finally:
        coordinator.dispose()
        lock.release()


def test_authorized_preparation_records_only_opaque_phase2_metadata(
    phase2_settings: Phase2Settings,
) -> None:
    class EligibleJobPort:
        def authorization_for_resume(self, job_id: str) -> VerifiedJobPreparationAuthorization:
            return VerifiedJobPreparationAuthorization(
                job_id=job_id,
                job_revision_id="sanitized-revision-1",
                authorization_id="sanitized-authorization-1",
                eligibility="eligible",
                expires_at=datetime(2026, 8, 24, 9, 15, tzinfo=UTC),
                activation_generation=7,
            )

        def revalidate_resume_authorization(
            self, expected: VerifiedJobPreparationAuthorization
        ) -> VerifiedJobPreparationAuthorization:
            return expected

    with _coordinator(phase2_settings) as coordinator:
        service = ResumePreparationService(
            EligibleJobPort(),
            ResumePreparationAttemptStore(coordinator),
            now=lambda: datetime(2026, 8, 24, 9, 0, tzinfo=UTC),
        )

        attempt = service.start(job_id="sanitized-job-1", resume_kind="tailored")

        with coordinator._session_factory() as session:
            stored = session.get(Phase2ResumePreparationAttempt, attempt.id)

    assert stored is not None
    assert stored.job_id == "sanitized-job-1"
    assert stored.job_revision_id == "sanitized-revision-1"
    assert stored.authorization_id == "sanitized-authorization-1"
    assert stored.activation_generation == 7
    assert set(stored.__table__.columns.keys()) == {
        "id",
        "job_id",
        "job_revision_id",
        "authorization_id",
        "authorization_expires_at",
        "activation_generation",
        "created_at",
    }
