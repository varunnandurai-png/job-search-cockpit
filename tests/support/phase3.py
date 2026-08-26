from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image
from sqlalchemy.orm import Session

from job_search_cockpit.phase1_contract.snapshots import (
    Phase1ResumeFactProjection,
    Phase1ResumeFactProjectionRequest,
    Phase1ResumeFactSnapshot,
)
from job_search_cockpit.phase2.config import Phase2Settings
from job_search_cockpit.phase2.database import create_phase2_engine, upgrade_phase2_database
from job_search_cockpit.phase2.finalisation import LocalResumeFinalisationService
from job_search_cockpit.phase2.models import (
    Phase2DiscoveryRun,
    Phase2JobRecord,
    Phase2JobRevision,
    Phase2ResumeRequirementLedger,
    Phase2SourceListingObservation,
)
from job_search_cockpit.phase2.mutation import Phase2InstanceLock, Phase2MutationCoordinator
from job_search_cockpit.phase2.resume_safety import VerifiedJobPreparationAuthorization


@dataclass(slots=True)
class SyntheticPreparationPort:
    authorizations: dict[str, VerifiedJobPreparationAuthorization]

    def authorization_for_resume(self, job_id: str) -> VerifiedJobPreparationAuthorization:
        return self.authorizations[job_id]

    def revalidate_resume_authorization(
        self, expected: VerifiedJobPreparationAuthorization
    ) -> VerifiedJobPreparationAuthorization:
        return self.authorizations[expected.job_id]


@dataclass(slots=True)
class SyntheticPhase1Port:
    projection: Phase1ResumeFactProjection

    def resume_fact_projection(
        self, request: Phase1ResumeFactProjectionRequest
    ) -> Phase1ResumeFactProjection:
        assert request.requirement_ids == self.projection.requirement_ids
        return self.projection

    def revalidate_resume_fact_projection(
        self, expected: Phase1ResumeFactProjection
    ) -> Phase1ResumeFactProjection:
        return self.projection


@dataclass(slots=True)
class SyntheticPhase3Runtime:
    service: LocalResumeFinalisationService
    preparation_port: SyntheticPreparationPort
    phase1_port: SyntheticPhase1Port
    coordinator: Phase2MutationCoordinator
    lock: Phase2InstanceLock
    headshot_path: Path

    def close(self) -> None:
        self.coordinator.dispose()
        self.lock.release()


def build_synthetic_phase3_runtime(tmp_path: Path) -> SyntheticPhase3Runtime:
    settings = Phase2Settings(tmp_path / "data")
    upgrade_phase2_database(f"sqlite:///{settings.database_path}")
    engine = create_phase2_engine(settings)
    lock = Phase2InstanceLock.acquire(settings)
    coordinator = Phase2MutationCoordinator(settings, engine, lock)
    requirement_id = "skills.python"
    projection = Phase1ResumeFactProjection(
        requirement_ids=(requirement_id,),
        facts=(
            Phase1ResumeFactSnapshot(
                requirement_id=requirement_id,
                claim_id="claim-1",
                revision_id="fact-revision-1",
                support_assertion_id="support-1",
                safe_wording="Built Python services.",
                employer_key="employer-1",
                period_start="2024-01",
                period_end="2025-01",
            ),
        ),
        profile_fingerprint="a" * 64,
        profile_generation=1,
        readiness_fingerprint="b" * 64,
        readiness_generation=1,
        authority_fingerprint="c" * 64,
        authority_generation=1,
        restore_generation=0,
        fingerprint="d" * 64,
    )
    authorizations = {
        "job-1": _authorization("job-1", "job-revision-1", "authorization-1", "Product Manager"),
        "job-2": _authorization(
            "job-2", "job-revision-2", "authorization-2", "Lead Product Manager"
        ),
    }
    preparation_port = SyntheticPreparationPort(authorizations)
    phase1_port = SyntheticPhase1Port(projection)
    _seed_catalog(coordinator, authorizations.values())
    headshot_path = tmp_path / "synthetic-headshot.png"
    Image.new("RGB", (120, 120), color=(210, 220, 230)).save(headshot_path)
    return SyntheticPhase3Runtime(
        service=LocalResumeFinalisationService(
            preparation_port,
            phase1_port,  # type: ignore[arg-type]
            coordinator,
            settings.final_resume_dir,
        ),
        preparation_port=preparation_port,
        phase1_port=phase1_port,
        coordinator=coordinator,
        lock=lock,
        headshot_path=headshot_path,
    )


def _authorization(
    job_id: str, revision_id: str, authorization_id: str, role_name: str
) -> VerifiedJobPreparationAuthorization:
    return VerifiedJobPreparationAuthorization(
        job_id=job_id,
        job_revision_id=revision_id,
        selected_location_path_fingerprint="e" * 64,
        authorization_id=authorization_id,
        authorization_nonce=f"nonce-{authorization_id}",
        eligibility="eligible",
        expires_at=datetime(2099, 1, 1, tzinfo=UTC),
        phase1_profile_fingerprint="a" * 64,
        phase1_profile_generation=1,
        phase1_readiness_fingerprint="b" * 64,
        phase1_readiness_generation=1,
        phase1_authority_fingerprint="c" * 64,
        phase1_authority_generation=1,
        phase1_restore_generation=0,
        phase2_activation_generation=1,
        phase2_restore_generation=0,
        requirement_ids=("skills.python",),
        requirement_ledger_fingerprint="f" * 64,
        company_name="Acme & Co.",
        role_name=role_name,
    )


def _seed_catalog(
    coordinator: Phase2MutationCoordinator,
    authorizations: object,
) -> None:
    def insert(session: Session) -> None:
        session.add(
            Phase2DiscoveryRun(
                id="run-1",
                phase1_profile_fingerprint="a" * 64,
                phase1_profile_generation=1,
                phase1_readiness_fingerprint="b" * 64,
                phase1_readiness_generation=1,
                phase1_authority_fingerprint="c" * 64,
                phase1_authority_generation=1,
                phase1_restore_generation=0,
                phase2_activation_generation=1,
                phase2_restore_generation=0,
            )
        )
        session.flush()
        for index, authorization in enumerate(authorizations, start=1):
            assert isinstance(authorization, VerifiedJobPreparationAuthorization)
            observation_id = f"observation-{index}"
            session.add(
                Phase2SourceListingObservation(
                    id=observation_id,
                    discovery_run_id="run-1",
                    provider_id="synthetic-provider",
                    provider_run_id=None,
                    source_listing_id=f"listing-{index}",
                    canonical_url=f"https://example.test/jobs/{index}",
                    title=authorization.role_name,
                    employer_name=authorization.company_name,
                    locations_json=["Bengaluru"],
                    posted_at=None,
                    public_description="Synthetic public description.",
                    compensation_text=None,
                    retrieved_at=datetime(2026, 8, 26, tzinfo=UTC),
                    raw_content_fingerprint=str(index) * 64,
                    content_fingerprint=str(index + 2) * 64,
                )
            )
            session.add(
                Phase2JobRecord(
                    id=authorization.job_id,
                    posting_identity_fingerprint=str(index + 4) * 64,
                )
            )
            session.flush()
            session.add(
                Phase2JobRevision(
                    id=authorization.job_revision_id,
                    job_record_id=authorization.job_id,
                    source_observation_id=observation_id,
                    canonical_url=f"https://example.test/jobs/{index}",
                    title=authorization.role_name,
                    employer_name=authorization.company_name,
                    locations_json=["Bengaluru"],
                    posted_at=None,
                    public_description="Synthetic public description.",
                    compensation_text=None,
                    content_fingerprint=str(index + 6) * 64,
                )
            )
            session.flush()
            session.add(
                Phase2ResumeRequirementLedger(
                    id=f"ledger-{index}",
                    job_id=authorization.job_id,
                    job_revision_id=authorization.job_revision_id,
                    requirement_ids_json=list(authorization.requirement_ids),
                    requirement_ledger_fingerprint=authorization.requirement_ledger_fingerprint,
                    phase2_activation_generation=1,
                    phase2_restore_generation=0,
                )
            )

    coordinator.run(insert, "seed_synthetic_phase3")
