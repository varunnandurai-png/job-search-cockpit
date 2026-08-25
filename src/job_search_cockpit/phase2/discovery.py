from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from job_search_cockpit.phase1_contract.snapshots import (
    Phase1ActivationInputs,
    canonical_fingerprint,
)
from job_search_cockpit.phase2.activation import Phase2ActivationService
from job_search_cockpit.phase2.config import Phase2Settings
from job_search_cockpit.phase2.discovery_types import ProviderListing, ProviderRequest
from job_search_cockpit.phase2.models import (
    Phase2DiscoveryRun,
    Phase2JobRecord,
    Phase2JobRevision,
    Phase2SourceListingObservation,
)
from job_search_cockpit.phase2.mutation import Phase2MutationCoordinator
from job_search_cockpit.phase2.provider_config import ProviderCredentials, ProviderLimits
from job_search_cockpit.phase2.providers import (
    APIFY_GLASSDOOR_ACTOR,
    APIFY_LINKEDIN_ACTOR,
    APIFY_NAUKRI_ACTOR,
    ApifyProvider,
    JSearchProvider,
    create_provider_http_client,
)
from job_search_cockpit.phase2.types import Phase2Action, Phase2ActivationUnavailable
from job_search_cockpit.ports import Phase1MatchingPort


class ListingProvider(Protocol):
    def fetch(
        self,
        request: ProviderRequest,
        credentials: ProviderCredentials,
        client: httpx.Client,
    ) -> tuple[ProviderListing, ...]: ...


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    discovery_run_id: str
    provider_counts: dict[str, int]
    observation_count: int
    revision_count: int


@dataclass(frozen=True, slots=True)
class _ProviderPlan:
    provider_id: str
    request: ProviderRequest
    provider: ListingProvider


class DiscoveryService:
    def __init__(
        self,
        settings: Phase2Settings,
        phase1_port: Phase1MatchingPort | None = None,
        activation_service: Phase2ActivationService | None = None,
        coordinator: Phase2MutationCoordinator | None = None,
        *,
        credentials: ProviderCredentials | None = None,
        dotenv_path: Path | None = None,
        client_factory: Callable[[], httpx.Client] = create_provider_http_client,
    ) -> None:
        self.settings = settings
        self.phase1_port = phase1_port
        self.activation_service = activation_service
        self.coordinator = coordinator
        self.credentials = credentials
        self.dotenv_path = dotenv_path
        self._client_factory = client_factory

    @classmethod
    def unavailable_for_tests(cls, settings: Phase2Settings) -> DiscoveryService:
        return cls(settings)

    def run_micro_pilot(self) -> DiscoveryResult:
        return self._run(
            listing_limit=ProviderLimits().micro_listing_limit,
            charge_limit=ProviderLimits().micro_apify_charge_usd,
        )

    def run_weekly_pilot(self) -> DiscoveryResult:
        return self._run(
            listing_limit=None,
            charge_limit=ProviderLimits().max_apify_charge_usd,
        )

    def _run(self, listing_limit: int | None, charge_limit: Decimal) -> DiscoveryResult:
        self._require_available()
        assert self.activation_service is not None
        assert self.phase1_port is not None
        assert self.coordinator is not None
        activation_service = self.activation_service
        phase1_port = self.phase1_port

        activation_service.revalidate_before(Phase2Action.DISCOVERY)
        expected_phase1 = phase1_port.activation_inputs()
        plans = self._plans(expected_phase1, listing_limit, charge_limit)
        credentials = self.credentials or ProviderCredentials.from_environment(
            dotenv_path=self.dotenv_path
        )
        observations: list[tuple[str, ProviderListing]] = []
        with self._client_factory() as client:
            for plan in plans:
                activation_service.revalidate_before(Phase2Action.DISCOVERY)
                listings = plan.provider.fetch(plan.request, credentials, client)
                observations.extend((plan.provider_id, listing) for listing in listings)

        def persist(session: Session) -> DiscoveryResult:
            activation_service.revalidate_before(Phase2Action.DISCOVERY)
            phase1_port.revalidate_activation_inputs(expected_phase1)
            run = Phase2DiscoveryRun(
                id=str(uuid4()),
                **_phase1_run_fields(expected_phase1),
                phase2_activation_generation=activation_service.activation_view().activation_generation,
                phase2_restore_generation=activation_service.activation_view().restore_generation,
            )
            session.add(run)
            session.flush()
            observation_count = 0
            revision_count = 0
            for provider_id, listing in observations:
                created, revision = _persist_listing(session, run.id, provider_id, listing)
                observation_count += created
                revision_count += revision
            return DiscoveryResult(
                discovery_run_id=run.id,
                provider_counts=_counts(observations),
                observation_count=observation_count,
                revision_count=revision_count,
            )

        return self.coordinator.run(persist, "phase2_provider_discovery")

    def _require_available(self) -> None:
        if self.activation_service is None or self.phase1_port is None or self.coordinator is None:
            raise Phase2ActivationUnavailable("Phase II provider access is unavailable.")

    def _plans(
        self,
        inputs: Phase1ActivationInputs,
        listing_limit: int | None,
        charge_limit: Decimal,
    ) -> tuple[_ProviderPlan, ...]:
        role = inputs.profile.payload.eligible_roles[0]
        location = inputs.profile.payload.locations[0]
        limits = ProviderLimits()
        count = listing_limit or limits.linkedin_listing_limit
        return (
            _ProviderPlan(
                "apify-linkedin",
                ProviderRequest(
                    "apify-linkedin", role, location, count, charge_limit
                ),
                ApifyProvider(APIFY_LINKEDIN_ACTOR),
            ),
            _ProviderPlan(
                "apify-naukri",
                ProviderRequest(
                    "apify-naukri", role, location,
                    listing_limit or limits.naukri_listing_limit, charge_limit
                ),
                ApifyProvider(APIFY_NAUKRI_ACTOR),
            ),
            _ProviderPlan(
                "apify-glassdoor",
                ProviderRequest(
                    "apify-glassdoor",
                    role,
                    location,
                    listing_limit or limits.glassdoor_listing_limit,
                    charge_limit,
                ),
                ApifyProvider(APIFY_GLASSDOOR_ACTOR),
            ),
            _ProviderPlan(
                "jsearch",
                ProviderRequest(
                    "jsearch", role, location, listing_limit or limits.jsearch_listing_limit
                ),
                JSearchProvider(),
            ),
        )


def _phase1_run_fields(inputs: Phase1ActivationInputs) -> dict[str, object]:
    return {
        "phase1_profile_fingerprint": inputs.profile.fingerprint,
        "phase1_profile_generation": inputs.profile.active_profile_generation,
        "phase1_readiness_fingerprint": inputs.readiness.fingerprint,
        "phase1_readiness_generation": inputs.readiness.readiness_generation,
        "phase1_authority_fingerprint": inputs.acceptance_receipt.fingerprint,
        "phase1_authority_generation": inputs.readiness.authority_high_water_mark,
        "phase1_restore_generation": inputs.readiness.restore_generation,
    }


def _persist_listing(
    session: Session, run_id: str, provider_id: str, listing: ProviderListing
) -> tuple[int, int]:
    raw_fingerprint = _listing_fingerprint(listing)
    observation = session.scalar(
        select(Phase2SourceListingObservation).where(
            Phase2SourceListingObservation.provider_id == provider_id,
            Phase2SourceListingObservation.source_listing_id == listing.provider_listing_id,
            Phase2SourceListingObservation.content_fingerprint == raw_fingerprint,
        )
    )
    if observation is not None:
        return 0, 0

    observation = Phase2SourceListingObservation(
        id=str(uuid4()),
        discovery_run_id=run_id,
        provider_id=provider_id,
        provider_run_id=None,
        source_listing_id=listing.provider_listing_id,
        canonical_url=listing.canonical_url,
        title=listing.title,
        employer_name=listing.employer_name,
        locations_json=list(listing.locations),
        posted_at=listing.posted_at,
        public_description=listing.public_description,
        compensation_text=listing.compensation_text,
        retrieved_at=listing.retrieved_at,
        raw_content_fingerprint=raw_fingerprint,
        content_fingerprint=raw_fingerprint,
    )
    session.add(observation)
    identity = _identity_fingerprint(listing)
    job = session.scalar(
        select(Phase2JobRecord).where(Phase2JobRecord.posting_identity_fingerprint == identity)
    )
    if job is None:
        job = Phase2JobRecord(id=str(uuid4()), posting_identity_fingerprint=identity)
        session.add(job)
        session.flush()
    revision = session.scalar(
        select(Phase2JobRevision).where(
            Phase2JobRevision.job_record_id == job.id,
            Phase2JobRevision.content_fingerprint == raw_fingerprint,
        )
    )
    if revision is None:
        session.add(
            Phase2JobRevision(
                id=str(uuid4()),
                job_record_id=job.id,
                source_observation_id=observation.id,
                canonical_url=listing.canonical_url,
                title=listing.title,
                employer_name=listing.employer_name,
                locations_json=list(listing.locations),
                posted_at=listing.posted_at,
                public_description=listing.public_description,
                compensation_text=listing.compensation_text,
                content_fingerprint=raw_fingerprint,
            )
        )
        return 1, 1
    return 1, 0


def _identity_fingerprint(listing: ProviderListing) -> str:
    return sha256(
        f"{listing.canonical_url}\0{listing.provider_listing_id}".encode()
    ).hexdigest()


def _listing_fingerprint(listing: ProviderListing) -> str:
    return canonical_fingerprint(
        {
            "canonical_url": listing.canonical_url,
            "title": listing.title.strip(),
            "employer_name": listing.employer_name.strip(),
            "locations": tuple(location.strip() for location in listing.locations),
            "posted_at": listing.posted_at.isoformat() if listing.posted_at else None,
            "public_description": listing.public_description.strip(),
            "compensation_text": listing.compensation_text.strip()
            if listing.compensation_text
            else None,
        }
    )


def _counts(observations: list[tuple[str, ProviderListing]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for provider_id, _listing in observations:
        counts[provider_id] = counts.get(provider_id, 0) + 1
    return counts


__all__ = ["DiscoveryResult", "DiscoveryService"]
