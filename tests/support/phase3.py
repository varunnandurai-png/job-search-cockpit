import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from PIL import Image
from sqlalchemy.orm import Session

from job_search_cockpit.phase1_contract.service import Phase1ContractService
from job_search_cockpit.phase1_contract.snapshots import (
    Phase1ResumeFactProjection,
    Phase1ResumeFactProjectionRequest,
    Phase1ResumeFactSnapshot,
)
from job_search_cockpit.phase2.config import Phase2Settings
from job_search_cockpit.phase2.database import create_phase2_engine, upgrade_phase2_database
from job_search_cockpit.phase2.discovery import DiscoveryService
from job_search_cockpit.phase2.discovery_types import ProviderListing, ProviderRequest
from job_search_cockpit.phase2.drive_api import DriveFileMetadata
from job_search_cockpit.phase2.drive_auth import DriveAuthorizationRequest
from job_search_cockpit.phase2.drive_backup import DriveBackupStore, FinalResumeDriveBackupService
from job_search_cockpit.phase2.finalisation import (
    FINALISE_CONFIRMATION,
    LocalResumeFinalisationService,
)
from job_search_cockpit.phase2.models import (
    Phase2DiscoveryRun,
    Phase2JobRecord,
    Phase2JobRevision,
    Phase2ResumeRequirementLedger,
    Phase2SourceListingObservation,
)
from job_search_cockpit.phase2.mutation import Phase2InstanceLock, Phase2MutationCoordinator
from job_search_cockpit.phase2.provider_config import ProviderCredentials
from job_search_cockpit.phase2.resume_safety import VerifiedJobPreparationAuthorization
from job_search_cockpit.phase2.runtime import Phase2Runtime
from job_search_cockpit.ports import PreparedVault
from job_search_cockpit.storage.models import Claim
from tests.support.web import AuthenticatedClient, authenticated_test_app


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


@dataclass(slots=True)
class _FakePublicProvider:
    listing: ProviderListing
    requests: list[ProviderRequest]

    def fetch(
        self,
        request: ProviderRequest,
        credentials: ProviderCredentials,
        client: httpx.Client,
    ) -> tuple[ProviderListing, ...]:
        del credentials, client
        self.requests.append(request)
        if request.provider_id.startswith("apify"):
            assert request.listing_limit <= 5
            assert request.max_charge_usd is not None and request.max_charge_usd <= 0.10
        return (self.listing,) if request.provider_id == "apify-linkedin" else ()


class _FakeDriveAuthorization:
    def access_token(self, before_request: Any) -> str:
        before_request()
        return "fake-drive-access-token"

    def begin(
        self, operation_id: str, session_id: str, redirect_uri: str
    ) -> DriveAuthorizationRequest:
        raise AssertionError("The injected Drive credential is already available.")

    def complete(self, state: str, code: str, session_id: str, before_request: Any) -> str:
        raise AssertionError("The fake Drive workflow does not use OAuth.")

    def deny(self, state: str, reason_code: str, session_id: str) -> str:
        raise AssertionError("The fake Drive workflow does not use OAuth.")


@dataclass(slots=True)
class _FakeDriveClient:
    finalisation_service: LocalResumeFinalisationService

    def generate_ids(
        self, access_token: str, count: int, *, before_request: Any
    ) -> tuple[str, ...]:
        assert access_token == "fake-drive-access-token"
        assert count == 3
        before_request()
        return ("fake-folder", "fake-docx", "fake-pdf")

    def create_or_verify_folder(
        self, access_token: str, folder_id: str, *, before_request: Any
    ) -> DriveFileMetadata:
        assert access_token == "fake-drive-access-token"
        assert folder_id == "fake-folder"
        before_request()
        return DriveFileMetadata(
            id=folder_id,
            name="Job Search Cockpit",
            mime_type="application/vnd.google-apps.folder",
            parents=(),
            size=None,
            sha256=None,
            trashed=False,
            shared=False,
            app_authorized=True,
        )

    def upload_verified_file(
        self,
        *,
        access_token: str,
        file_id: str,
        folder_id: str,
        final_artifact_id: str,
        file_kind: str,
        before_request: Any,
    ) -> DriveFileMetadata:
        assert access_token == "fake-drive-access-token"
        assert folder_id == "fake-folder"
        before_request()
        artifact = self.finalisation_service.artifact_by_id(final_artifact_id)
        if file_kind == "docx":
            path, size, checksum = (
                artifact.docx_path,
                artifact.docx_byte_length,
                artifact.docx_sha256,
            )
            mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            path, size, checksum = artifact.pdf_path, artifact.pdf_byte_length, artifact.pdf_sha256
            mime_type = "application/pdf"
        return DriveFileMetadata(
            id=file_id,
            name=path.name,
            mime_type=mime_type,
            parents=(folder_id,),
            size=size,
            sha256=checksum,
            trashed=False,
            shared=False,
            app_authorized=True,
        )

    def reconcile_folder(
        self, access_token: str, folder_id: str, *, before_request: Any
    ) -> DriveFileMetadata | None:
        raise AssertionError("The deterministic acceptance backup never needs a retry.")

    def reconcile_verified_file(
        self,
        access_token: str,
        file_id: str,
        *,
        final_artifact_id: str,
        file_kind: str,
        folder_id: str,
        before_request: Any,
    ) -> DriveFileMetadata | None:
        raise AssertionError("The deterministic acceptance backup never needs a retry.")


@contextmanager
def phase1_to_phase4_cockpit(settings: Any) -> Iterator[AuthenticatedClient]:
    def configure(prepared: PreparedVault) -> None:
        runtime = prepared.phase2_runtime
        assert isinstance(runtime, Phase2Runtime)
        listing = ProviderListing(
            provider_listing_id="acceptance-listing-1",
            canonical_url="https://jobs.example.test/listings/acceptance-1",
            title="Senior Product Manager",
            employer_name="Example Employer",
            locations=("Hyderabad",),
            posted_at=datetime(2026, 8, 29, tzinfo=UTC),
            public_description="You will own the platform.",
            compensation_text=None,
            retrieved_at=datetime(2026, 8, 30, tzinfo=UTC),
        )
        fake_providers = {
            provider_id: _FakePublicProvider(listing, [])
            for provider_id in ("apify-linkedin", "apify-naukri", "apify-glassdoor", "jsearch")
        }

        def client_factory() -> httpx.Client:
            client = httpx.Client(
                transport=httpx.MockTransport(lambda request: httpx.Response(599))
            )
            runtime.provider_http_clients.append(client)
            return client

        runtime.discovery_service = DiscoveryService(
            Phase2Settings(settings.data_dir),
            runtime.phase1_port,
            runtime.activation_service,
            runtime.coordinator,
            credentials=ProviderCredentials("fake-apify-token", "fake-jsearch-key"),
            providers=fake_providers,
            client_factory=client_factory,
        )
        runtime.drive_backup_service = FinalResumeDriveBackupService(
            finalisation_service=runtime.resume_finalisation_service,
            authorization_service=_FakeDriveAuthorization(),
            drive_client=_FakeDriveClient(runtime.resume_finalisation_service),
            store=DriveBackupStore(runtime.coordinator),
        )

    with authenticated_test_app(settings, configure_prepared=configure) as client:
        yield client


def complete_phase1_acceptance(authenticated_cockpit: AuthenticatedClient) -> None:
    preview = authenticated_cockpit.post("/imports/preview")
    assert preview.status_code == 200
    applied = authenticated_cockpit.post(
        "/imports/apply",
        data={"preview_id": preview.headers["x-preview-id"]},
        follow_redirects=False,
    )
    assert applied.status_code == 303
    while match := re.search(r'href="/review/([^"]+)"', authenticated_cockpit.get("/review").text):
        claim_id = match.group(1)
        page = authenticated_cockpit.get(f"/review/{claim_id}")
        if "These sources disagree" in page.text:
            selected = _required_input(page.text, "selected_revision_id")
            response = authenticated_cockpit.post(
                f"/review/{claim_id}/resolve-conflict",
                data={
                    "selected_revision_id": selected,
                    "group_id": _required_input(page.text, "group_id"),
                    "expected_group_version": _required_input(page.text, "expected_group_version"),
                    "reason": "Use the first supported fixture revision.",
                },
                follow_redirects=False,
            )
            assert response.status_code == 303
            page = authenticated_cockpit.get(f"/review/{claim_id}")
        sensitivity_version = _form_input(
            page.text, f"/review/{claim_id}/sensitivity", "expected_version"
        )
        assert sensitivity_version is not None
        response = authenticated_cockpit.post(
            f"/review/{claim_id}/sensitivity",
            data={"sensitivity": "normal", "expected_version": sensitivity_version},
            follow_redirects=False,
        )
        assert response.status_code == 303
        page = authenticated_cockpit.get(f"/review/{claim_id}")
        coordinator = authenticated_cockpit.client.app.state.prepared.coordinator
        with coordinator._session_factory() as session:
            claim = session.get(Claim, claim_id)
            assert claim is not None
            approve = claim.canonical_key == (
                "employment.example-commerce.led-last-mile-platform-modernization-supporting-annual-gmv"
            )
        endpoint = "approve" if approve else "reject"
        data = {
            "expected_version": _required_input(page.text, "expected_version"),
            "reason": "Outside the deterministic Phase I evidence projection.",
        }
        if approve:
            data["revision_id"] = _required_input(page.text, "revision_id")
        response = authenticated_cockpit.post(
            f"/review/{claim_id}/{endpoint}", data=data, follow_redirects=False
        )
        assert response.status_code == 303
    prepared = authenticated_cockpit.client.app.state.prepared
    service = prepared.services.phase1_contract_service
    assert isinstance(service, Phase1ContractService)
    service.record_acceptance(
        acceptance_run_id="phase1-to-phase4-local-acceptance",
        result_fingerprint="e" * 64,
        actor="Varun",
        confirmation="I ACCEPT THE PHASE I ACCEPTANCE RECEIPT",
    )
    assert "Your verified profile is ready for Phase 2" in authenticated_cockpit.get("/").text


def select_first_eligible_candidate(
    authenticated_cockpit: AuthenticatedClient, review: Any
) -> tuple[str, str]:
    match = re.search(r'data-candidate="([^"]+)"', review.text)
    assert match is not None
    revision_id = match.group(1)
    runtime = authenticated_cockpit.client.app.state.prepared.phase2_runtime
    assert isinstance(runtime, Phase2Runtime)
    with runtime.coordinator._session_factory() as session:
        revision = session.get(Phase2JobRevision, revision_id)
        assert revision is not None
        return revision_id, revision.job_record_id


def complete_local_manual_mapping(
    authenticated_cockpit: AuthenticatedClient, revision_id: str
) -> None:
    started = authenticated_cockpit.post(
        "/phase-2/mapping-attempts",
        data={"job_revision_id": revision_id},
        follow_redirects=False,
    )
    assert started.status_code == 303
    mapping_path = started.headers["location"]
    assert mapping_path != "/phase-2/review"
    mapping = authenticated_cockpit.get(mapping_path)
    requirements = re.findall(r'name="relation:([^"]+)"', mapping.text)
    assert requirements
    response = authenticated_cockpit.post(
        mapping_path,
        data={
            item: value
            for requirement_id in requirements
            for item, value in (
                (f"relation:{requirement_id}", "direct"),
                (f"reason:{requirement_id}", "direct/exact_capability_performed"),
                (f"choice:{requirement_id}", "0"),
            )
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text


def verification_form(revision_id: str) -> dict[str, str]:
    return {
        "job_revision_id": revision_id,
        "reason": "Verified public listing and eligible Hyderabad location.",
        "confirmation": "VERIFY JOB FOR PHASE II PREPARATION",
    }


def assert_requirement_ledger_uses_phase1_projection(
    authenticated_cockpit: AuthenticatedClient, job_id: str
) -> None:
    runtime = authenticated_cockpit.client.app.state.prepared.phase2_runtime
    assert isinstance(runtime, Phase2Runtime)
    authorization = runtime.verified_job_preparation_port.authorization_for_resume(job_id)
    projection = runtime.phase1_port.resume_fact_projection(
        Phase1ResumeFactProjectionRequest(requirement_ids=authorization.requirement_ids)
    )
    assert projection.requirement_ids == authorization.requirement_ids
    assert {fact.requirement_id for fact in projection.facts} == set(authorization.requirement_ids)


def finalise_with_test_headshot(
    authenticated_cockpit: AuthenticatedClient, started: Any
) -> Any:
    review_path = started.headers["location"]
    data_dir = authenticated_cockpit.client.app.state.settings.data_dir
    headshot_path = Path(data_dir) / "e2e-headshot.png"
    Image.new("RGB", (120, 120), color=(210, 220, 230)).save(headshot_path)
    response = authenticated_cockpit.post(
        f"{review_path}/finalise",
        data={
            "confirmation": FINALISE_CONFIRMATION,
            "headshot_path": str(headshot_path),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    return authenticated_cockpit.get(review_path)


def request_fake_drive_backup(authenticated_cockpit: AuthenticatedClient, finalised: Any) -> Any:
    artifact_id = _required_input(finalised.text, "final_artifact_id")
    response = authenticated_cockpit.post(
        "/phase-2/drive-backups",
        data={"final_artifact_id": artifact_id},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return authenticated_cockpit.get(str(finalised.url))


def _required_input(page: str, name: str) -> str:
    match = re.search(rf'name="{re.escape(name)}" value="([^"]+)"', page)
    assert match is not None
    return match.group(1)


def _form_input(page: str, action: str, name: str) -> str | None:
    match = re.search(
        rf'<form[^>]+action="{re.escape(action)}".*?name="{re.escape(name)}" value="([^"]+)"',
        page,
        flags=re.DOTALL,
    )
    return match.group(1) if match is not None else None
