from datetime import UTC, datetime

import pytest

from job_search_cockpit.phase2.provider_instances import (
    ApprovedProviderInstance,
    OfficialProviderKind,
    ProviderInstanceApproval,
)


def test_provider_instance_approval_rejects_a_non_digest_fingerprint() -> None:
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

    with pytest.raises(ValueError, match="SHA-256 digest"):
        ProviderInstanceApproval(
            instance=instance,
            approval_fingerprint="z" * 64,
            enabled=False,
            actor="local-user",
            reason="approved provider boundary",
            approved_at=datetime.now(UTC),
        )


def test_approved_provider_instance_rejects_a_wildcard_content_type() -> None:
    with pytest.raises(ValueError, match="exact content types"):
        ApprovedProviderInstance(
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
            content_types=("application/*",),
        )


def test_approved_provider_instance_rejects_wildcard_hosts_and_non_https_endpoint() -> None:
    with pytest.raises(ValueError, match="exact HTTPS host"):
        ApprovedProviderInstance(
            instance_id="employer-greenhouse-v1",
            kind=OfficialProviderKind.GREENHOUSE_PUBLIC_BOARD,
            employer_identity="Example Employer",
            hosts=("*.greenhouse.io",),
            endpoint_url="http://boards-api.greenhouse.io/v1/boards/example/jobs",
            redirect_hosts=(),
            path_prefixes=("/v1/boards/example/jobs",),
            parser_version="greenhouse-public-v1",
            max_response_bytes=1_000_000,
            min_request_interval_seconds=30,
        )
