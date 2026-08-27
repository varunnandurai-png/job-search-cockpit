from ipaddress import ip_address

import pytest

from job_search_cockpit.phase2.provider_instances import (
    ApprovedProviderInstance,
    OfficialProviderKind,
)
from job_search_cockpit.phase2.safe_transport import (
    ContainedOfficialTransport,
    InertOfficialResponse,
    ProviderContainmentError,
)


def test_transport_rejects_a_private_dns_answer_before_request() -> None:
    instance = ApprovedProviderInstance(
        instance_id="employer-greenhouse-v1",
        kind=OfficialProviderKind.GREENHOUSE_PUBLIC_BOARD,
        employer_identity="Example Employer",
        hosts=("boards-api.greenhouse.io",),
        endpoint_url="https://boards-api.greenhouse.io/v1/boards/example/jobs",
        redirect_hosts=(),
        path_prefixes=("/v1/boards/example/jobs",),
        parser_version="greenhouse-public-v1",
        max_response_bytes=1_000_000,
        min_request_interval_seconds=30,
    )
    transport = ContainedOfficialTransport(
        resolver=lambda _host: (ip_address("127.0.0.1"),),
        executor=_forbidden_executor,
        revalidate=lambda: None,
    )

    with pytest.raises(ProviderContainmentError, match="public address"):
        transport.fetch(instance, instance.endpoint_url)


def _forbidden_executor(_request: object) -> object:
    raise AssertionError("transport must reject before attempting a request")


def test_transport_accepts_an_exact_instance_declared_content_type() -> None:
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
    transport = ContainedOfficialTransport(
        resolver=lambda _host: (ip_address("8.8.8.8"),),
        executor=lambda _request: InertOfficialResponse(
            status_code=200,
            headers={"content-type": "text/html; charset=utf-8"},
            body=b"{}",
            connected_address=ip_address("8.8.8.8"),
        ),
        revalidate=lambda: None,
    )

    response = transport.fetch(instance, instance.endpoint_url)

    assert response.body == b"{}"


def test_transport_revalidates_before_resolution_request_and_response_acceptance() -> None:
    instance = ApprovedProviderInstance(
        instance_id="employer-greenhouse-v1",
        kind=OfficialProviderKind.GREENHOUSE_PUBLIC_BOARD,
        employer_identity="Example Employer",
        hosts=("boards-api.greenhouse.io",),
        endpoint_url="https://boards-api.greenhouse.io/v1/boards/example/jobs",
        redirect_hosts=(),
        path_prefixes=("/v1/boards/example/jobs",),
        parser_version="greenhouse-public-v1",
        max_response_bytes=1_000_000,
        min_request_interval_seconds=30,
    )
    checks: list[str] = []
    transport = ContainedOfficialTransport(
        resolver=lambda _host: (ip_address("8.8.8.8"),),
        executor=lambda _request: InertOfficialResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body=b"{}",
            connected_address=ip_address("8.8.8.8"),
        ),
        revalidate=lambda: checks.append("checked"),
    )

    transport.fetch(instance, instance.endpoint_url)

    assert checks == ["checked", "checked", "checked"]


def test_transport_rejects_a_bare_sensitive_query_parameter_before_request() -> None:
    instance = ApprovedProviderInstance(
        instance_id="employer-greenhouse-v1",
        kind=OfficialProviderKind.GREENHOUSE_PUBLIC_BOARD,
        employer_identity="Example Employer",
        hosts=("boards-api.greenhouse.io",),
        endpoint_url="https://boards-api.greenhouse.io/v1/boards/example/jobs",
        redirect_hosts=(),
        path_prefixes=("/v1/boards/example/jobs",),
        parser_version="greenhouse-public-v1",
        max_response_bytes=1_000_000,
        min_request_interval_seconds=30,
    )
    transport = ContainedOfficialTransport(
        resolver=lambda _host: (ip_address("8.8.8.8"),),
        executor=_forbidden_executor,
        revalidate=lambda: None,
    )

    with pytest.raises(ProviderContainmentError, match="containment policy"):
        transport.fetch(instance, f"{instance.endpoint_url}?token")
