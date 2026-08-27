import pytest

from job_search_cockpit.phase2.official_providers import (
    GreenhousePublicBoardAdapter,
    LeverPublicBoardAdapter,
    OfficialProviderAdapterRegistry,
)
from job_search_cockpit.phase2.provider_instances import (
    ApprovedProviderInstance,
    OfficialProviderKind,
    ProviderInstanceUnavailable,
)


def test_adapter_registry_rejects_an_instance_without_a_matching_kind() -> None:
    registry = OfficialProviderAdapterRegistry.empty()

    with pytest.raises(ProviderInstanceUnavailable, match="not registered"):
        registry.adapter_for(OfficialProviderKind.GREENHOUSE_PUBLIC_BOARD)


def test_greenhouse_adapter_requires_the_exact_instance_endpoint() -> None:
    instance = ApprovedProviderInstance(
        instance_id="employer-greenhouse-v1",
        kind=OfficialProviderKind.GREENHOUSE_PUBLIC_BOARD,
        employer_identity="Example Employer",
        hosts=("boards-api.greenhouse.io",),
        endpoint_url="https://boards-api.greenhouse.io/v1/boards/example/jobs?content=true",
        redirect_hosts=(),
        path_prefixes=("/v1/boards/example/jobs",),
        parser_version="greenhouse-public-v1",
        max_response_bytes=1_000_000,
        min_request_interval_seconds=30,
        source_identifier="example",
    )

    assert GreenhousePublicBoardAdapter().endpoint_for(instance) == instance.endpoint_url


def test_lever_adapter_requires_the_exact_instance_endpoint() -> None:
    instance = ApprovedProviderInstance(
        instance_id="employer-lever-v1",
        kind=OfficialProviderKind.LEVER_PUBLIC_BOARD,
        employer_identity="Example Employer",
        hosts=("api.lever.co",),
        endpoint_url="https://api.lever.co/v0/postings/example?mode=json",
        redirect_hosts=(),
        path_prefixes=("/v0/postings/example",),
        parser_version="lever-public-v1",
        max_response_bytes=1_000_000,
        min_request_interval_seconds=30,
        source_identifier="example",
    )

    assert LeverPublicBoardAdapter().endpoint_for(instance) == instance.endpoint_url


def test_endpoint_adapter_registry_contains_only_greenhouse_and_lever_contracts() -> None:
    registry = OfficialProviderAdapterRegistry.with_public_board_adapters()

    assert isinstance(
        registry.adapter_for(OfficialProviderKind.GREENHOUSE_PUBLIC_BOARD),
        GreenhousePublicBoardAdapter,
    )
    assert isinstance(
        registry.adapter_for(OfficialProviderKind.LEVER_PUBLIC_BOARD),
        LeverPublicBoardAdapter,
    )
    with pytest.raises(ProviderInstanceUnavailable, match="not registered"):
        registry.adapter_for(OfficialProviderKind.OFFICIAL_PAGE_READ_ONLY)


def test_official_page_adapter_requires_an_exact_registered_parser_before_transport() -> None:
    instance = ApprovedProviderInstance(
        instance_id="employer-careers-v1",
        kind=OfficialProviderKind.OFFICIAL_PAGE_READ_ONLY,
        employer_identity="Example Employer",
        hosts=("careers.example.com",),
        endpoint_url="https://careers.example.com/jobs",
        redirect_hosts=(),
        path_prefixes=("/jobs",),
        parser_version="official-page-v1",
        max_response_bytes=1_000_000,
        min_request_interval_seconds=30,
        content_types=("text/html",),
    )

    with pytest.raises(ProviderInstanceUnavailable, match="parser is not registered"):
        OfficialProviderAdapterRegistry.with_direct_source_adapters().fetch(
            instance, _forbidden_transport
        )


def test_official_page_adapter_rejects_a_registered_parser_with_the_wrong_version() -> None:
    instance = ApprovedProviderInstance(
        instance_id="employer-careers-v1",
        kind=OfficialProviderKind.OFFICIAL_PAGE_READ_ONLY,
        employer_identity="Example Employer",
        hosts=("careers.example.com",),
        endpoint_url="https://careers.example.com/jobs",
        redirect_hosts=(),
        path_prefixes=("/jobs",),
        parser_version="official-page-v1",
        max_response_bytes=1_000_000,
        min_request_interval_seconds=30,
        content_types=("text/html",),
    )
    registry = OfficialProviderAdapterRegistry.with_direct_source_adapters().with_parser(
        instance.instance_id, "official-page-v2", lambda _instance, _response: ()
    )

    with pytest.raises(ProviderInstanceUnavailable, match="parser version is not approved"):
        registry.fetch(instance, _forbidden_transport)


def _forbidden_transport(_instance: object, _url: str) -> object:
    raise AssertionError("parser registration must be checked before transport")
