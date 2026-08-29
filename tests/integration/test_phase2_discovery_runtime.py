from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select

from job_search_cockpit.config import Settings
from job_search_cockpit.phase1_contract.service import Phase1ContractUnavailable
from job_search_cockpit.phase1_contract.snapshots import (
    Phase1AcceptanceReceiptSnapshot,
    Phase1ActivationInputs,
    Phase1ReadinessSnapshot,
    SearchProfileSnapshot,
)
from job_search_cockpit.phase2.activation import Phase2ActivationService
from job_search_cockpit.phase2.config import Phase2Settings
from job_search_cockpit.phase2.database import create_phase2_engine, upgrade_phase2_database
from job_search_cockpit.phase2.discovery import DiscoveryService
from job_search_cockpit.phase2.discovery_types import ProviderListing, ProviderRequest
from job_search_cockpit.phase2.models import (
    Phase2AuthorityState,
    Phase2DiscoveryRun,
    Phase2JobRecord,
    Phase2JobRevision,
    Phase2SourceListingObservation,
)
from job_search_cockpit.phase2.mutation import Phase2InstanceLock, Phase2MutationCoordinator
from job_search_cockpit.phase2.provider_config import ProviderCredentials
from job_search_cockpit.phase2.providers import (
    ProviderResponseError,
    create_provider_http_client,
)
from job_search_cockpit.phase2.runtime import prepare_phase2_runtime
from job_search_cockpit.phase2.types import ActivationCommand, Phase2ActivationUnavailable
from job_search_cockpit.search_profile.catalog import build_profile_v1


class _FixturePhase1Port:
    def __init__(self) -> None:
        self.current = Phase1ActivationInputs(
            acceptance_receipt=Phase1AcceptanceReceiptSnapshot(
                id="receipt-1",
                application_build="test-build",
                schema_revision="0002_phase1_contract",
                acceptance_suite_version="phase1-acceptance-test-v1",
                acceptance_run_id="run-1",
                result_fingerprint="r" * 64,
                restore_high_water_mark=0,
                accepted_at="2026-08-24T00:00:00+00:00",
                fingerprint="a" * 64,
            ),
            readiness=Phase1ReadinessSnapshot(
                ready_for_phase_2=True,
                manifest_version="four-source-v1",
                import_run_id="import-1",
                source_hashes={"assessment": "s" * 64},
                active_profile_version=1,
                readiness_generation=1,
                authority_high_water_mark=1,
                restore_generation=0,
                fingerprint="d" * 64,
            ),
            profile=SearchProfileSnapshot(
                version_number=1,
                payload=build_profile_v1(),
                active_profile_generation=1,
                fingerprint="p" * 64,
            ),
        )

    def activation_inputs(self) -> Phase1ActivationInputs:
        return self.current

    def revalidate_activation_inputs(
        self, expected: Phase1ActivationInputs
    ) -> Phase1ActivationInputs:
        if self.current != expected:
            raise Phase1ContractUnavailable("The Phase I activation inputs changed.")
        return self.current


@dataclass(slots=True)
class _DiscoveryRuntime:
    discovery_service: DiscoveryService
    coordinator: Phase2MutationCoordinator
    instance_lock: Phase2InstanceLock
    provider_clients: list[httpx.Client]
    phase1_port: _FixturePhase1Port

    def close(self) -> None:
        for client in self.provider_clients:
            client.close()
        self.coordinator.dispose()
        self.instance_lock.release()


@dataclass(slots=True)
class _FakeProvider:
    listings: tuple[ProviderListing, ...] = ()
    failure_code: str | None = None
    requests: list[ProviderRequest] | None = None
    on_fetch: Callable[[], None] | None = None

    def fetch(
        self,
        request: ProviderRequest,
        credentials: ProviderCredentials,
        client: httpx.Client,
    ) -> tuple[ProviderListing, ...]:
        del credentials, client
        if self.requests is not None:
            self.requests.append(request)
        if self.on_fetch is not None:
            callback = self.on_fetch
            self.on_fetch = None
            callback()
        if self.failure_code is not None:
            raise ProviderResponseError(self.failure_code)
        return self.listings


VALID_LISTING = ProviderListing(
    provider_listing_id="listing-1",
    canonical_url="https://jobs.example.com/listings/1",
    title="Senior Product Manager",
    employer_name="Example Employer",
    locations=("Hyderabad",),
    posted_at=datetime(2026, 8, 28, tzinfo=UTC),
    public_description="Own the public product roadmap.",
    compensation_text=None,
    retrieved_at=datetime(2026, 8, 29, tzinfo=UTC),
)


@pytest.fixture
def runtime(phase2_settings: Phase2Settings) -> Iterator[_DiscoveryRuntime]:
    upgrade_phase2_database(f"sqlite:///{phase2_settings.database_path}")
    engine = create_phase2_engine(phase2_settings)
    instance_lock = Phase2InstanceLock.acquire(phase2_settings)
    coordinator = Phase2MutationCoordinator(phase2_settings, engine, instance_lock)
    phase1_port = _FixturePhase1Port()
    activation_service = Phase2ActivationService(phase1_port, coordinator)
    activation_service.activate(
        ActivationCommand(actor="Varun", confirmation="ENABLE PHASE II")
    )
    value = _DiscoveryRuntime(
        discovery_service=DiscoveryService(
            phase2_settings,
            phase1_port,
            activation_service,
            coordinator,
        ),
        coordinator=coordinator,
        instance_lock=instance_lock,
        provider_clients=[],
        phase1_port=phase1_port,
    )
    try:
        yield value
    finally:
        value.close()


@pytest.fixture
def fake_providers() -> dict[str, _FakeProvider]:
    return {
        "apify-linkedin": _FakeProvider(requests=[]),
        "apify-naukri": _FakeProvider(requests=[]),
        "apify-glassdoor": _FakeProvider(requests=[]),
        "jsearch": _FakeProvider(requests=[]),
    }


@pytest.fixture
def configured_runtime(
    phase2_settings: Phase2Settings,
    fake_providers: dict[str, _FakeProvider],
) -> Iterator[_DiscoveryRuntime]:
    upgrade_phase2_database(f"sqlite:///{phase2_settings.database_path}")
    engine = create_phase2_engine(phase2_settings)
    instance_lock = Phase2InstanceLock.acquire(phase2_settings)
    coordinator = Phase2MutationCoordinator(phase2_settings, engine, instance_lock)
    phase1_port = _FixturePhase1Port()
    activation_service = Phase2ActivationService(phase1_port, coordinator)
    activation_service.activate(
        ActivationCommand(actor="Varun", confirmation="ENABLE PHASE II")
    )
    provider_clients: list[httpx.Client] = []

    def client_factory() -> httpx.Client:
        client = create_provider_http_client()
        provider_clients.append(client)
        return client

    discovery_service = DiscoveryService(
        phase2_settings,
        phase1_port,
        activation_service,
        coordinator,
    )
    discovery_service.credentials = ProviderCredentials("test-apify", "test-jsearch")
    discovery_service.providers = fake_providers
    discovery_service._client_factory = client_factory
    value = _DiscoveryRuntime(
        discovery_service=discovery_service,
        coordinator=coordinator,
        instance_lock=instance_lock,
        provider_clients=provider_clients,
        phase1_port=phase1_port,
    )
    try:
        yield value
    finally:
        value.close()


def test_micro_plans_cover_active_profile_roles_and_locations(
    runtime: _DiscoveryRuntime,
) -> None:
    plans = runtime.discovery_service.plans_for_test(micro=True)

    expected_role_query = (
        "Senior Product Manager OR Lead Product Manager — individual contributor OR "
        "Selected Principal Product Manager — individual contributor OR Applied AI Product "
        "Manager with domain overlap OR Senior Technical Product Manager — platforms, APIs, "
        "integrations, data, fintech, lending, commerce, or fulfilment"
    )
    assert [plan.provider_id for plan in plans] == [
        "apify-linkedin",
        "apify-naukri",
        "apify-glassdoor",
        "jsearch",
    ]
    assert {plan.request.location_id for plan in plans} == {
        "Hyderabad",
        "Bengaluru",
        "Singapore",
    }
    assert {plan.request.role_query_id for plan in plans} == {expected_role_query}
    assert all(
        plan.request.listing_limit == 5
        and str(plan.request.max_charge_usd) == "0.10"
        for plan in plans
        if plan.provider_id.startswith("apify")
    )


def test_micro_plans_preserve_profile_order_without_duplicate_requests(
    runtime: _DiscoveryRuntime,
) -> None:
    plans = runtime.discovery_service.plans_for_test(micro=True)
    request_keys = [
        (plan.provider_id, plan.request.role_query_id, plan.request.location_id)
        for plan in plans
    ]

    assert [(provider_id, location_id) for provider_id, _role, location_id in request_keys] == [
        ("apify-linkedin", "Hyderabad"),
        ("apify-naukri", "Bengaluru"),
        ("apify-glassdoor", "Singapore"),
        ("jsearch", "Hyderabad"),
    ]
    assert len(request_keys) == 4
    assert len(request_keys) == len(set(request_keys))


def test_one_provider_failure_preserves_other_provider_results(
    configured_runtime: _DiscoveryRuntime,
    fake_providers: dict[str, _FakeProvider],
) -> None:
    fake_providers["apify-linkedin"].failure_code = "timeout"
    fake_providers["jsearch"].listings = (VALID_LISTING,)

    result = configured_runtime.discovery_service.run_micro_pilot()

    assert result.provider_failures == {"apify-linkedin": "timeout"}
    assert result.provider_counts == {"jsearch": 1}
    assert result.observation_count == 1
    assert result.revision_count == 1


def test_all_provider_failures_still_append_a_discovery_run(
    configured_runtime: _DiscoveryRuntime,
    fake_providers: dict[str, _FakeProvider],
) -> None:
    failure_codes = {
        "apify-linkedin": "timeout",
        "apify-naukri": "quota_or_cost_limit",
        "apify-glassdoor": "schema_mismatch",
        "jsearch": "provider_unavailable",
    }
    for provider_id, failure_code in failure_codes.items():
        fake_providers[provider_id].failure_code = failure_code

    result = configured_runtime.discovery_service.run_micro_pilot()
    status = configured_runtime.discovery_service.status_view()

    assert result.provider_failures == failure_codes
    assert result.provider_counts == {}
    assert result.observation_count == 0
    assert result.revision_count == 0
    assert status.provider_configuration_available is True
    assert status.provider_failures == failure_codes
    with configured_runtime.coordinator._session_factory() as session:
        assert session.scalar(select(func.count(Phase2DiscoveryRun.id))) == 1


def test_repeated_listing_content_keeps_append_only_identity_and_revision_counts(
    configured_runtime: _DiscoveryRuntime,
    fake_providers: dict[str, _FakeProvider],
) -> None:
    fake_providers["jsearch"].listings = (VALID_LISTING,)

    first = configured_runtime.discovery_service.run_micro_pilot()
    second = configured_runtime.discovery_service.run_micro_pilot()

    assert (first.observation_count, first.revision_count) == (1, 1)
    assert (second.observation_count, second.revision_count) == (0, 0)
    with configured_runtime.coordinator._session_factory() as session:
        assert session.scalar(select(func.count(Phase2DiscoveryRun.id))) == 2
        assert session.scalar(select(func.count(Phase2SourceListingObservation.id))) == 1
        assert session.scalar(select(func.count(Phase2JobRecord.id))) == 1
        assert session.scalar(select(func.count(Phase2JobRevision.id))) == 1


def test_phase_one_drift_before_the_next_provider_aborts_without_a_run(
    configured_runtime: _DiscoveryRuntime,
    fake_providers: dict[str, _FakeProvider],
) -> None:
    def change_phase_one() -> None:
        current = configured_runtime.phase1_port.current
        configured_runtime.phase1_port.current = current.model_copy(
            update={
                "profile": current.profile.model_copy(
                    update={"active_profile_generation": 2}
                )
            }
        )

    fake_providers["apify-linkedin"].on_fetch = change_phase_one

    with pytest.raises(Phase2ActivationUnavailable, match="provider access is unavailable"):
        configured_runtime.discovery_service.run_micro_pilot()

    with configured_runtime.coordinator._session_factory() as session:
        assert session.scalar(select(func.count(Phase2DiscoveryRun.id))) == 0


def test_phase_two_generation_drift_before_the_next_provider_aborts_without_a_run(
    configured_runtime: _DiscoveryRuntime,
    fake_providers: dict[str, _FakeProvider],
) -> None:
    def change_phase_two() -> None:
        with (
            configured_runtime.coordinator._session_factory() as session,
            session.begin(),
        ):
            state = session.get(Phase2AuthorityState, 1)
            assert state is not None
            state.activation_generation += 1

    fake_providers["apify-linkedin"].on_fetch = change_phase_two

    with pytest.raises(Phase2ActivationUnavailable, match="changed during discovery"):
        configured_runtime.discovery_service.run_micro_pilot()

    with configured_runtime.coordinator._session_factory() as session:
        assert session.scalar(select(func.count(Phase2DiscoveryRun.id))) == 0


@pytest.mark.parametrize("dotenv_present", [False, True])
def test_runtime_derives_optional_dotenv_and_closes_run_clients(
    phase2_settings: Phase2Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_providers: dict[str, _FakeProvider],
    dotenv_present: bool,
) -> None:
    if dotenv_present:
        dotenv = phase2_settings.data_dir / ".env"
        dotenv.parent.mkdir(parents=True)
        dotenv.write_text(
            "APIFY_API_TOKEN=test-apify\nJSEARCH_API_KEY=test-jsearch\n",
            encoding="utf-8",
        )
        dotenv.chmod(0o600)
    else:
        monkeypatch.setenv("APIFY_API_TOKEN", "test-apify")
        monkeypatch.setenv("JSEARCH_API_KEY", "test-jsearch")
    captured_settings: list[Phase2Settings | None] = []

    def load_credentials(
        cls: type[ProviderCredentials],
        environment=None,
        *,
        phase2_settings: Phase2Settings | None = None,
    ) -> ProviderCredentials:
        del cls, environment
        captured_settings.append(phase2_settings)
        return ProviderCredentials("test-apify", "test-jsearch")

    monkeypatch.setattr(
        ProviderCredentials,
        "from_environment",
        classmethod(load_credentials),
    )
    settings = Settings.for_tests(
        phase2_settings.data_dir, tmp_path / "sanitized-sources"
    )
    phase1_port = _FixturePhase1Port()
    runtime = prepare_phase2_runtime(settings, phase1_port)
    client: httpx.Client | None = None
    try:
        assert captured_settings == []
        runtime.activation_service.activate(
            ActivationCommand(actor="Varun", confirmation="ENABLE PHASE II")
        )
        runtime.discovery_service.providers = fake_providers

        runtime.discovery_service.run_micro_pilot()

        expected_settings = phase2_settings if dotenv_present else None
        assert captured_settings == [expected_settings]
        clients = getattr(runtime, "provider_http_clients", [])
        assert len(clients) == 1
        client = clients[0]
        assert client.is_closed is False
    finally:
        runtime.close()
    assert client is not None
    assert client.is_closed is True


@pytest.mark.parametrize(
    ("environment", "expected_status", "expected_available"),
    [
        ({}, "missing", False),
        ({"APIFY_API_TOKEN": "test-apify"}, "partial", False),
        (
            {
                "APIFY_API_TOKEN": "test-apify",
                "JSEARCH_API_KEY": "test-jsearch",
            },
            "available",
            True,
        ),
    ],
)
def test_configuration_status_reports_availability_without_values(
    phase2_settings: Phase2Settings,
    monkeypatch: pytest.MonkeyPatch,
    environment: dict[str, str],
    expected_status: str,
    expected_available: bool,
) -> None:
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    monkeypatch.delenv("JSEARCH_API_KEY", raising=False)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    service = DiscoveryService.unavailable_for_tests(phase2_settings)

    status = service.status_view()

    assert status.provider_configuration_status == expected_status
    assert status.provider_configuration_available is expected_available
    assert "test-apify" not in repr(status)
    assert "test-jsearch" not in repr(status)


def test_partial_credentials_skip_only_the_missing_provider(
    configured_runtime: _DiscoveryRuntime,
    fake_providers: dict[str, _FakeProvider],
) -> None:
    configured_runtime.discovery_service.credentials = ProviderCredentials(
        "test-apify", ""
    )

    result = configured_runtime.discovery_service.run_micro_pilot()

    assert result.provider_failures == {"jsearch": "authentication_failed"}
    assert fake_providers["jsearch"].requests == []
    assert all(
        len(fake_providers[provider_id].requests or []) == 1
        for provider_id in ("apify-linkedin", "apify-naukri", "apify-glassdoor")
    )
