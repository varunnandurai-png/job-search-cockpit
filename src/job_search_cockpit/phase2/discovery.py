from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from job_search_cockpit.phase1_contract.snapshots import (
    Phase1ActivationInputs,
    canonical_fingerprint,
)
from job_search_cockpit.phase2.activation import Phase2ActivationService
from job_search_cockpit.phase2.config import Phase2Settings
from job_search_cockpit.phase2.discovery_types import ProviderListing
from job_search_cockpit.phase2.models import (
    Phase2DiscoveryRun,
    Phase2JobRecord,
    Phase2JobRevision,
    Phase2JobVerification,
    Phase2ProviderInstanceApproval,
    Phase2SourceListingObservation,
)
from job_search_cockpit.phase2.mutation import Phase2MutationCoordinator
from job_search_cockpit.phase2.official_providers import OfficialProviderAdapterRegistry
from job_search_cockpit.phase2.provider_config import ProviderConfigurationError
from job_search_cockpit.phase2.provider_instances import (
    ApprovedProviderInstance,
    OfficialProviderKind,
    ProviderInstanceUnavailable,
)
from job_search_cockpit.phase2.types import Phase2Action, Phase2ActivationUnavailable
from job_search_cockpit.ports import Phase1MatchingPort


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    discovery_run_id: str
    provider_counts: dict[str, int]
    observation_count: int
    revision_count: int


@dataclass(frozen=True, slots=True)
class DiscoveryStatusView:
    provider_configuration_available: bool
    last_run_at: datetime | None
    last_run_counts: dict[str, int]
    candidate_count: int
    verification_count: int


@dataclass(frozen=True, slots=True)
class _OfficialProviderPlan:
    provider_id: str
    instance: ApprovedProviderInstance


class DiscoveryService:
    def __init__(
        self,
        settings: Phase2Settings,
        phase1_port: Phase1MatchingPort | None = None,
        activation_service: Phase2ActivationService | None = None,
        coordinator: Phase2MutationCoordinator | None = None,
        adapter_registry: OfficialProviderAdapterRegistry | None = None,
    ) -> None:
        self.settings = settings
        self.phase1_port = phase1_port
        self.activation_service = activation_service
        self.coordinator = coordinator
        self.adapter_registry = (
            adapter_registry or OfficialProviderAdapterRegistry.with_direct_source_adapters()
        )

    @classmethod
    def unavailable_for_tests(cls, settings: Phase2Settings) -> DiscoveryService:
        return cls(settings)

    def run_micro_pilot(self) -> DiscoveryResult:
        return self._run()

    def run_weekly_pilot(self) -> DiscoveryResult:
        return self._run()

    def status_view(self) -> DiscoveryStatusView:
        configured = self._provider_configuration_available()
        if self.coordinator is None:
            return DiscoveryStatusView(configured, None, {}, 0, 0)
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
            )

    def _run(self) -> DiscoveryResult:
        self._require_available()
        assert self.activation_service is not None
        assert self.phase1_port is not None
        assert self.coordinator is not None
        activation_service = self.activation_service
        phase1_port = self.phase1_port

        activation_service.revalidate_before(Phase2Action.DISCOVERY)
        expected_phase1 = phase1_port.activation_inputs()
        self._plans(expected_phase1)
        raise ProviderConfigurationError(
            "Official provider execution is unavailable until a named instance and parser are "
            "approved."
        )

    def _require_available(self) -> None:
        if self.activation_service is None or self.phase1_port is None or self.coordinator is None:
            raise Phase2ActivationUnavailable("Phase II provider access is unavailable.")

    def _provider_configuration_available(self) -> bool:
        try:
            return bool(self._approved_instances())
        except (ProviderConfigurationError, ProviderInstanceUnavailable):
            return False

    def _plans(self, inputs: Phase1ActivationInputs) -> tuple[_OfficialProviderPlan, ...]:
        del inputs
        instances = self._approved_instances()
        if not instances:
            raise ProviderConfigurationError("no approved official provider instances are enabled")
        plans: list[_OfficialProviderPlan] = []
        for instance in instances:
            self.adapter_registry.adapter_for(instance.kind)
            plans.append(_OfficialProviderPlan(instance.instance_id, instance))
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
        raise ProviderConfigurationError(
            "approved official provider metadata is invalid"
        ) from error


def _string_tuple(value: list[object]) -> tuple[str, ...]:
    strings = tuple(item for item in value if isinstance(item, str))
    if len(strings) != len(value):
        raise ValueError("approved official provider metadata is invalid")
    return strings


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
