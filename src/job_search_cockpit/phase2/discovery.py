from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from typing import Literal, Protocol
from uuid import uuid4

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from job_search_cockpit.phase1_contract.snapshots import (
    Phase1ActivationInputs,
    canonical_fingerprint,
)
from job_search_cockpit.phase2.activation import Phase2ActivationService
from job_search_cockpit.phase2.config import Phase2Settings
from job_search_cockpit.phase2.discovery_types import (
    ProviderListing,
    ProviderOutcome,
    ProviderRequest,
)
from job_search_cockpit.phase2.models import (
    Phase2DiscoveryRun,
    Phase2JobRecord,
    Phase2JobRevision,
    Phase2JobVerification,
    Phase2ProviderInstanceApproval,
    Phase2SourceListingObservation,
)
from job_search_cockpit.phase2.mutation import Phase2MutationCoordinator
from job_search_cockpit.phase2.provider_config import (
    ProviderConfigurationError,
    ProviderCredentials,
    ProviderLimits,
    read_provider_env_file,
)
from job_search_cockpit.phase2.provider_instances import (
    ApprovedProviderInstance,
    OfficialProviderKind,
)
from job_search_cockpit.phase2.providers import (
    APIFY_GLASSDOOR_ACTOR,
    APIFY_LINKEDIN_ACTOR,
    APIFY_NAUKRI_ACTOR,
    ApifyProvider,
    JSearchProvider,
    ProviderResponseError,
    create_provider_http_client,
)
from job_search_cockpit.phase2.types import (
    Phase2Action,
    Phase2ActivationUnavailable,
    Phase2ActivationView,
)
from job_search_cockpit.ports import Phase1MatchingPort


class DiscoveryUnavailable(ValueError):
    """Raised when no approved official provider can be used."""


_MAX_ROLE_QUERY_LENGTH = 512
ProviderConfigurationStatus = Literal["available", "missing", "partial"]


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    discovery_run_id: str
    provider_counts: dict[str, int]
    observation_count: int
    revision_count: int
    provider_failures: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DiscoveryStatusView:
    provider_configuration_available: bool
    last_run_at: datetime | None
    last_run_counts: dict[str, int]
    candidate_count: int
    verification_count: int
    provider_failures: dict[str, str] = field(default_factory=dict)
    provider_configuration_status: ProviderConfigurationStatus = "missing"


class ListingProvider(Protocol):
    def fetch(
        self,
        request: ProviderRequest,
        credentials: ProviderCredentials,
        client: httpx.Client,
    ) -> tuple[ProviderListing, ...]: ...


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
        credential_settings: Phase2Settings | None = None,
        providers: Mapping[str, ListingProvider] | None = None,
        client_factory: Callable[[], httpx.Client] = create_provider_http_client,
    ) -> None:
        self.settings = settings
        self.phase1_port = phase1_port
        self.activation_service = activation_service
        self.coordinator = coordinator
        self.credentials = credentials
        self.credential_settings = credential_settings
        self.providers = dict(providers) if providers is not None else _default_providers()
        self._client_factory = client_factory
        self._last_provider_failures: dict[str, str] = {}

    @classmethod
    def unavailable_for_tests(cls, settings: Phase2Settings) -> DiscoveryService:
        return cls(settings)

    def run_micro_pilot(self) -> DiscoveryResult:
        return self._run(micro=True)

    def run_weekly_pilot(self) -> DiscoveryResult:
        return self._run(micro=False)

    def plans_for_test(self, *, micro: bool) -> tuple[_ProviderPlan, ...]:
        if self.phase1_port is None:
            raise Phase2ActivationUnavailable("Phase II provider access is unavailable.")
        return self._plans(self.phase1_port.activation_inputs(), micro=micro)

    def status_view(self) -> DiscoveryStatusView:
        configuration_status = self._provider_configuration_status()
        configured = configuration_status == "available"
        if self.coordinator is None:
            return DiscoveryStatusView(
                configured,
                None,
                {},
                0,
                0,
                {},
                configuration_status,
            )
        with self.coordinator._session_factory() as session:
            run = session.scalar(
                select(Phase2DiscoveryRun).order_by(
                    Phase2DiscoveryRun.created_at.desc(), Phase2DiscoveryRun.id.desc()
                )
            )
            counts = (
                {
                    provider_id: int(count)
                    for provider_id, count in session.execute(
                        select(
                            Phase2SourceListingObservation.provider_id,
                            func.count(Phase2SourceListingObservation.id),
                        )
                        .where(Phase2SourceListingObservation.discovery_run_id == run.id)
                        .group_by(Phase2SourceListingObservation.provider_id)
                    )
                }
                if run is not None
                else {}
            )
            return DiscoveryStatusView(
                provider_configuration_available=configured,
                last_run_at=run.created_at if run is not None else None,
                last_run_counts=counts,
                candidate_count=int(session.scalar(select(func.count(Phase2JobRecord.id))) or 0),
                verification_count=int(
                    session.scalar(select(func.count(Phase2JobVerification.id))) or 0
                ),
                provider_failures=dict(self._last_provider_failures),
                provider_configuration_status=configuration_status,
            )

    def _run(self, *, micro: bool) -> DiscoveryResult:
        self._require_available()
        assert self.activation_service is not None
        assert self.phase1_port is not None
        assert self.coordinator is not None
        activation_service = self.activation_service
        phase1_port = self.phase1_port

        expected_phase2 = activation_service.revalidate_before(Phase2Action.DISCOVERY)
        expected_phase1 = phase1_port.activation_inputs()
        plans = self._plans(expected_phase1, micro=micro)
        credentials = self._credentials_for_run()
        outcomes: list[ProviderOutcome] = []
        client = self._client_factory()
        for plan in plans:
            current_phase2 = activation_service.revalidate_before(Phase2Action.DISCOVERY)
            _require_same_phase2_generation(current_phase2, expected_phase2)
            phase1_port.revalidate_activation_inputs(expected_phase1)
            if not _provider_credential_available(plan.provider_id, credentials):
                outcomes.append(
                    ProviderOutcome(plan.provider_id, failure_code="authentication_failed")
                )
                continue
            try:
                listings = plan.provider.fetch(plan.request, credentials, client)
            except ProviderResponseError as error:
                outcomes.append(ProviderOutcome(plan.provider_id, failure_code=error.code))
            else:
                outcomes.append(ProviderOutcome(plan.provider_id, listings=listings))

        def persist(session: Session) -> DiscoveryResult:
            current_phase2 = activation_service.revalidate_before(Phase2Action.DISCOVERY)
            _require_same_phase2_generation(current_phase2, expected_phase2)
            phase1_port.revalidate_activation_inputs(expected_phase1)
            run = Phase2DiscoveryRun(
                id=str(uuid4()),
                **_phase1_run_fields(expected_phase1),
                phase2_activation_generation=current_phase2.activation_generation,
                phase2_restore_generation=current_phase2.restore_generation,
            )
            session.add(run)
            session.flush()
            provider_counts: dict[str, int] = {}
            provider_failures: dict[str, str] = {}
            observation_count = 0
            revision_count = 0
            for outcome in outcomes:
                if outcome.failure_code is not None:
                    provider_failures.setdefault(outcome.provider_id, outcome.failure_code)
                    continue
                for listing in outcome.listings:
                    created, revision = _persist_listing(
                        session, run.id, outcome.provider_id, listing
                    )
                    observation_count += created
                    revision_count += revision
                    if created:
                        provider_counts[outcome.provider_id] = (
                            provider_counts.get(outcome.provider_id, 0) + created
                        )
            return DiscoveryResult(
                discovery_run_id=run.id,
                provider_counts=provider_counts,
                observation_count=observation_count,
                revision_count=revision_count,
                provider_failures=provider_failures,
            )

        result = self.coordinator.run(persist, "phase2_provider_discovery")
        self._last_provider_failures = dict(result.provider_failures)
        return result

    def _require_available(self) -> None:
        if self.activation_service is None or self.phase1_port is None or self.coordinator is None:
            raise Phase2ActivationUnavailable("Phase II provider access is unavailable.")

    def _provider_configuration_status(self) -> ProviderConfigurationStatus:
        apify_token, jsearch_key = self._credential_values()
        available_count = int(bool(apify_token)) + int(bool(jsearch_key))
        if available_count == 2:
            return "available"
        if available_count == 1:
            return "partial"
        return "missing"

    def _credential_values(self) -> tuple[str, str]:
        if self.credentials is not None:
            return self.credentials.apify_token, self.credentials.jsearch_key
        dotenv: dict[str, str] = {}
        try:
            if self.credential_settings is not None:
                dotenv = read_provider_env_file(self.credential_settings)
        except ProviderConfigurationError:
            return "", ""
        return (
            os.environ.get("APIFY_API_TOKEN") or dotenv.get("APIFY_API_TOKEN", ""),
            os.environ.get("JSEARCH_API_KEY") or dotenv.get("JSEARCH_API_KEY", ""),
        )

    def _credentials_for_run(self) -> ProviderCredentials:
        if self.credentials is not None:
            return self.credentials
        if self._provider_configuration_status() == "available":
            return ProviderCredentials.from_environment(
                phase2_settings=self.credential_settings
            )
        apify_token, jsearch_key = self._credential_values()
        return ProviderCredentials(apify_token, jsearch_key)

    def _plans(
        self, inputs: Phase1ActivationInputs, *, micro: bool
    ) -> tuple[_ProviderPlan, ...]:
        limits = ProviderLimits()
        apify_limit = (
            limits.micro_listing_limit if micro else limits.linkedin_listing_limit
        )
        charge_limit = (
            limits.micro_apify_charge_usd if micro else limits.max_apify_charge_usd
        )
        providers: tuple[tuple[str, ListingProvider], ...] = (
            ("apify-linkedin", self.providers["apify-linkedin"]),
            ("apify-naukri", self.providers["apify-naukri"]),
            ("apify-glassdoor", self.providers["apify-glassdoor"]),
            ("jsearch", self.providers["jsearch"]),
        )
        roles = tuple(
            dict.fromkeys(role.strip() for role in inputs.profile.payload.eligible_roles)
        )
        locations = tuple(
            dict.fromkeys(location.strip() for location in inputs.profile.payload.locations)
        )
        role_query = " OR ".join(roles)
        if not role_query or not locations:
            raise DiscoveryUnavailable(
                "the active search profile has no queryable roles or locations"
            )
        if len(role_query) > _MAX_ROLE_QUERY_LENGTH:
            raise DiscoveryUnavailable(
                "the active search profile role query exceeds 512 characters"
            )
        plans: list[_ProviderPlan] = []
        for index, (provider_id, provider) in enumerate(providers):
            listing_limit = (
                min(apify_limit, ProviderLimits.listing_limit_for(provider_id))
                if provider_id.startswith("apify")
                else limits.jsearch_listing_limit
            )
            plans.append(
                _ProviderPlan(
                    provider_id,
                    ProviderRequest(
                        provider_id,
                        role_query,
                        locations[index % len(locations)],
                        listing_limit,
                        charge_limit if provider_id.startswith("apify") else None,
                    ),
                    provider,
                )
            )
        return tuple(plans)

    def _approved_instances(self) -> tuple[ApprovedProviderInstance, ...]:
        if self.coordinator is None or self.activation_service is None:
            return ()
        view = self.activation_service.activation_view()
        with self.coordinator._session_factory() as session:
            approvals = session.scalars(
                select(Phase2ProviderInstanceApproval).order_by(
                    Phase2ProviderInstanceApproval.created_at.desc(),
                    Phase2ProviderInstanceApproval.id.desc(),
                )
            )
            latest: dict[str, Phase2ProviderInstanceApproval] = {}
            for approval in approvals:
                latest.setdefault(approval.instance_id, approval)
        return tuple(
            _approved_instance(approval)
            for _instance_id, approval in sorted(latest.items())
            if approval.enabled
            and approval.phase2_activation_generation == view.activation_generation
            and approval.phase2_restore_generation == view.restore_generation
        )


def _approved_instance(approval: Phase2ProviderInstanceApproval) -> ApprovedProviderInstance:
    try:
        return ApprovedProviderInstance(
            instance_id=approval.instance_id,
            kind=OfficialProviderKind(approval.provider_kind),
            employer_identity=approval.employer_identity,
            hosts=_string_tuple(approval.hosts_json),
            endpoint_url=approval.endpoint_url,
            redirect_hosts=_string_tuple(approval.redirect_hosts_json),
            path_prefixes=_string_tuple(approval.path_prefixes_json),
            parser_version=approval.parser_version,
            max_response_bytes=approval.max_response_bytes,
            min_request_interval_seconds=approval.min_request_interval_seconds,
            content_types=_string_tuple(approval.content_types_json),
            source_identifier=approval.source_identifier,
        )
    except (TypeError, ValueError) as error:
        raise DiscoveryUnavailable(
            "approved official provider metadata is invalid"
        ) from error


def _string_tuple(value: list[object]) -> tuple[str, ...]:
    strings = tuple(item for item in value if isinstance(item, str))
    if len(strings) != len(value):
        raise ValueError("approved official provider metadata is invalid")
    return strings


def _default_providers() -> dict[str, ListingProvider]:
    return {
        "apify-linkedin": ApifyProvider(APIFY_LINKEDIN_ACTOR),
        "apify-naukri": ApifyProvider(APIFY_NAUKRI_ACTOR),
        "apify-glassdoor": ApifyProvider(APIFY_GLASSDOOR_ACTOR),
        "jsearch": JSearchProvider(),
    }


def _require_same_phase2_generation(
    current: Phase2ActivationView, expected: Phase2ActivationView
) -> None:
    if (
        current.activation_generation != expected.activation_generation
        or current.restore_generation != expected.restore_generation
    ):
        raise Phase2ActivationUnavailable("Phase II activation changed during discovery.")


def _provider_credential_available(
    provider_id: str, credentials: ProviderCredentials
) -> bool:
    if provider_id.startswith("apify"):
        return bool(credentials.apify_token)
    return bool(credentials.jsearch_key)


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


__all__ = ["DiscoveryResult", "DiscoveryService", "DiscoveryStatusView"]
