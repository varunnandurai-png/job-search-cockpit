from dataclasses import dataclass

from job_search_cockpit.config import Settings
from job_search_cockpit.phase2.activation import Phase2ActivationService
from job_search_cockpit.phase2.application_drafts import (
    ApplicationDraftService,
    ApplicationDraftStore,
    ReusableAnswerService,
    ReusableAnswerStore,
)
from job_search_cockpit.phase2.config import Phase2Settings
from job_search_cockpit.phase2.database import create_phase2_engine, upgrade_phase2_database
from job_search_cockpit.phase2.mutation import Phase2InstanceLock, Phase2MutationCoordinator
from job_search_cockpit.phase2.resume_safety import (
    ResumePreparationAttemptStore,
    ResumePreparationService,
    VerifiedJobReadinessUnavailable,
)
from job_search_cockpit.ports import Phase1MatchingPort


@dataclass(slots=True)
class Phase2Runtime:
    coordinator: Phase2MutationCoordinator
    instance_lock: Phase2InstanceLock
    activation_service: Phase2ActivationService
    resume_preparation_service: ResumePreparationService
    reusable_answer_service: ReusableAnswerService
    application_draft_service: ApplicationDraftService

    def close(self) -> None:
        self.coordinator.dispose()
        self.instance_lock.release()


def prepare_phase2_runtime(settings: Settings, phase1_port: Phase1MatchingPort) -> Phase2Runtime:
    phase2_settings = Phase2Settings(data_dir=settings.data_dir)
    upgrade_phase2_database(f"sqlite:///{phase2_settings.database_path}")
    engine = create_phase2_engine(phase2_settings)
    instance_lock = Phase2InstanceLock.acquire(phase2_settings)
    coordinator = Phase2MutationCoordinator(phase2_settings, engine, instance_lock)
    preparation_port = VerifiedJobReadinessUnavailable()
    return Phase2Runtime(
        coordinator=coordinator,
        instance_lock=instance_lock,
        activation_service=Phase2ActivationService(phase1_port, coordinator),
        resume_preparation_service=ResumePreparationService(
            preparation_port, ResumePreparationAttemptStore(coordinator)
        ),
        reusable_answer_service=ReusableAnswerService(
            phase1_port, ReusableAnswerStore(coordinator)
        ),
        application_draft_service=ApplicationDraftService(
            preparation_port, ApplicationDraftStore(coordinator)
        ),
    )
