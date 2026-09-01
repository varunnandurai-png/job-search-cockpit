from dataclasses import dataclass, field

import httpx
from sqlalchemy import select

from job_search_cockpit.config import Settings
from job_search_cockpit.phase2.activation import Phase2ActivationService
from job_search_cockpit.phase2.application_drafts import (
    ApplicationDraftService,
    ApplicationDraftStore,
    ReusableAnswerService,
    ReusableAnswerStore,
)
from job_search_cockpit.phase2.assessment import (
    AssessmentAuthorityService,
    AssessmentPublicationService,
)
from job_search_cockpit.phase2.candidates import (
    CandidateWorkflowService,
    LocalManualMappingLaunch,
)
from job_search_cockpit.phase2.config import Phase2Settings
from job_search_cockpit.phase2.database import create_phase2_engine, upgrade_phase2_database
from job_search_cockpit.phase2.discovery import DiscoveryService
from job_search_cockpit.phase2.drive_api import DriveApiClient
from job_search_cockpit.phase2.drive_auth import (
    DriveAuthorizationService,
    MacOSKeychainCredentialStore,
)
from job_search_cockpit.phase2.drive_backup import DriveBackupStore, FinalResumeDriveBackupService
from job_search_cockpit.phase2.finalisation import LocalResumeFinalisationService
from job_search_cockpit.phase2.models import Phase2JobRevision
from job_search_cockpit.phase2.mutation import Phase2InstanceLock, Phase2MutationCoordinator
from job_search_cockpit.phase2.providers import create_provider_http_client
from job_search_cockpit.phase2.resume_safety import (
    ResumePreparationAttemptStore,
    ResumePreparationError,
    ResumePreparationService,
)
from job_search_cockpit.phase2.shortlist import AssessmentReviewService, SqlAssessmentReviewStore
from job_search_cockpit.phase2.verification import (
    CatalogVerifiedJobPreparationPort,
    VerifiedJobAuthorizationService,
)
from job_search_cockpit.ports import Phase1MatchingPort


@dataclass(slots=True)
class Phase2Runtime:
    coordinator: Phase2MutationCoordinator
    instance_lock: Phase2InstanceLock
    activation_service: Phase2ActivationService
    assessment_review_service: AssessmentReviewService
    candidate_workflow_service: CandidateWorkflowService
    discovery_service: DiscoveryService
    verified_job_authorization_service: VerifiedJobAuthorizationService
    resume_preparation_service: ResumePreparationService
    resume_finalisation_service: LocalResumeFinalisationService
    reusable_answer_service: ReusableAnswerService
    application_draft_service: ApplicationDraftService
    drive_backup_service: FinalResumeDriveBackupService | None
    drive_http_client: httpx.Client | None
    provider_http_clients: list[httpx.Client]
    phase1_port: Phase1MatchingPort
    verified_job_preparation_port: CatalogVerifiedJobPreparationPort
    # Wording releases are deliberately process-local and are never serialized.
    # Restarting the local app safely requires a new mapping authorization.
    local_manual_mapping_launches: dict[str, LocalManualMappingLaunch] = field(
        default_factory=dict
    )
    locally_mapped_job_revision_ids: set[str] = field(default_factory=set)

    def remember_local_manual_mapping(self, launch: LocalManualMappingLaunch) -> None:
        self.local_manual_mapping_launches[launch.attempt_id] = launch

    def local_manual_mapping(self, attempt_id: str) -> LocalManualMappingLaunch | None:
        return self.local_manual_mapping_launches.get(attempt_id)

    def forget_local_manual_mapping(self, attempt_id: str) -> None:
        self.local_manual_mapping_launches.pop(attempt_id, None)

    def mark_locally_mapped(self, job_revision_id: str) -> None:
        self.locally_mapped_job_revision_ids.add(job_revision_id)

    def current_candidate_source_urls(self) -> dict[str, str]:
        with self.coordinator._session_factory() as session:
            return {
                revision.id: revision.canonical_url
                for revision in session.scalars(select(Phase2JobRevision))
            }

    def verified_resume_job_id(self, job_revision_id: str) -> str | None:
        with self.coordinator._session_factory() as session:
            revision = session.get(Phase2JobRevision, job_revision_id)
            if revision is None:
                return None
            job_id = revision.job_record_id
        try:
            authorization = self.verified_job_preparation_port.authorization_for_resume(job_id)
        except ResumePreparationError:
            return None
        if (
            authorization.job_revision_id != job_revision_id
            or not authorization.requirement_ids
            or not authorization.requirement_ledger_fingerprint
        ):
            return None
        return job_id

    def close(self) -> None:
        for client in self.provider_http_clients:
            client.close()
        if self.drive_http_client is not None:
            self.drive_http_client.close()
        self.coordinator.dispose()
        self.instance_lock.release()


def prepare_phase2_runtime(settings: Settings, phase1_port: Phase1MatchingPort) -> Phase2Runtime:
    phase2_settings = Phase2Settings(data_dir=settings.data_dir)
    upgrade_phase2_database(f"sqlite:///{phase2_settings.database_path}")
    engine = create_phase2_engine(phase2_settings)
    instance_lock = Phase2InstanceLock.acquire(phase2_settings)
    coordinator = Phase2MutationCoordinator(phase2_settings, engine, instance_lock)
    activation_service = Phase2ActivationService(phase1_port, coordinator)
    assessment_authority_service = AssessmentAuthorityService(phase1_port, activation_service)
    assessment_publication_service = AssessmentPublicationService(
        assessment_authority_service, coordinator
    )
    provider_http_clients: list[httpx.Client] = []

    def provider_client_factory() -> httpx.Client:
        client = create_provider_http_client()
        provider_http_clients.append(client)
        return client

    preparation_port = CatalogVerifiedJobPreparationPort(
        phase1_port, activation_service, coordinator
    )
    verification_service = VerifiedJobAuthorizationService(
        phase1_port, activation_service, coordinator
    )
    finalisation_service = LocalResumeFinalisationService(
        preparation_port,
        phase1_port,
        coordinator,
        phase2_settings.final_resume_dir,
    )
    drive_http_client: httpx.Client | None = None
    drive_backup_service: FinalResumeDriveBackupService | None = None
    if settings.google_oauth_client_id:
        drive_http_client = httpx.Client(
            follow_redirects=False, timeout=httpx.Timeout(30.0, connect=10.0)
        )
        drive_backup_service = FinalResumeDriveBackupService(
            finalisation_service=finalisation_service,
            authorization_service=DriveAuthorizationService(
                client_id=settings.google_oauth_client_id,
                http_client=drive_http_client,
                credential_store=MacOSKeychainCredentialStore(),
            ),
            drive_client=DriveApiClient(drive_http_client, finalisation_service),
            store=DriveBackupStore(coordinator),
        )
    return Phase2Runtime(
        coordinator=coordinator,
        instance_lock=instance_lock,
        activation_service=activation_service,
        assessment_review_service=AssessmentReviewService(
            assessment_authority_service,
            SqlAssessmentReviewStore(engine),
        ),
        candidate_workflow_service=CandidateWorkflowService(
            phase1_port,
            activation_service,
            coordinator,
            assessment_publication_service,
        ),
        discovery_service=DiscoveryService(
            phase2_settings,
            phase1_port,
            activation_service,
            coordinator,
            credential_settings=(
                phase2_settings if (phase2_settings.data_dir / ".env").exists() else None
            ),
            client_factory=provider_client_factory,
        ),
        verified_job_authorization_service=verification_service,
        resume_preparation_service=ResumePreparationService(
            preparation_port, ResumePreparationAttemptStore(coordinator)
        ),
        resume_finalisation_service=finalisation_service,
        reusable_answer_service=ReusableAnswerService(
            phase1_port, ReusableAnswerStore(coordinator)
        ),
        application_draft_service=ApplicationDraftService(
            preparation_port, ApplicationDraftStore(coordinator)
        ),
        drive_backup_service=drive_backup_service,
        drive_http_client=drive_http_client,
        provider_http_clients=provider_http_clients,
        phase1_port=phase1_port,
        verified_job_preparation_port=preparation_port,
    )
