from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from job_search_cockpit.phase1_contract.snapshots import (
    Phase1AcceptanceReceiptSnapshot,
    Phase1ActivationInputs,
    Phase1ReadinessSnapshot,
    SearchProfileSnapshot,
)
from job_search_cockpit.phase2.config import Phase2Settings
from job_search_cockpit.phase2.discovery import DiscoveryService, _approved_instance
from job_search_cockpit.phase2.discovery_types import ProviderRequest
from job_search_cockpit.phase2.models import Phase2ProviderInstanceApproval
from job_search_cockpit.phase2.provider_config import (
    ProviderConfigurationError,
    ProviderCredentials,
    read_provider_env_file,
)
from job_search_cockpit.phase2.providers import (
    APIFY_GLASSDOOR_ACTOR,
    APIFY_LINKEDIN_ACTOR,
    APIFY_NAUKRI_ACTOR,
    ApifyProvider,
    JSearchProvider,
    create_provider_http_client,
)
from job_search_cockpit.search_profile.catalog import build_profile_v1


def test_provider_credentials_fail_closed_when_a_required_value_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)

    with pytest.raises(
        ProviderConfigurationError, match="Apify credentials are unavailable"
    ):
        ProviderCredentials.from_environment()


def test_provider_credentials_load_only_allowlisted_values_from_an_explicit_env_file(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# provider keys\nAPIFY_API_TOKEN='apify-secret'\nJSEARCH_API_KEY=rapid-secret\n",
        encoding="utf-8",
    )

    credentials = ProviderCredentials.from_environment({}, dotenv_path=env_file)

    assert credentials.apify_token == "apify-secret"
    assert credentials.jsearch_key == "rapid-secret"
    assert "apify-secret" not in repr(credentials)
    assert "rapid-secret" not in repr(credentials)
    with pytest.raises(FrozenInstanceError):
        credentials.apify_token = "changed"  # type: ignore[misc]


def test_provider_env_file_rejects_unknown_and_duplicate_keys(tmp_path: Path) -> None:
    unknown = tmp_path / "unknown.env"
    unknown.write_text("HOME=not-allowed\n", encoding="utf-8")
    duplicate = tmp_path / "duplicate.env"
    duplicate.write_text("APIFY_API_TOKEN=one\nAPIFY_API_TOKEN=two\n", encoding="utf-8")

    with pytest.raises(ProviderConfigurationError, match="unsupported key"):
        read_provider_env_file(unknown)
    with pytest.raises(ProviderConfigurationError, match="duplicate key"):
        read_provider_env_file(duplicate)


def test_provider_request_rejects_a_listing_limit_above_the_pilot_cap() -> None:
    with pytest.raises(ValueError, match="listing limit exceeds the approved pilot cap"):
        ProviderRequest(
            provider_id="apify-linkedin",
            role_query_id="senior-product-manager",
            location_id="bengaluru",
            listing_limit=41,
            max_charge_usd=Decimal("0.10"),
        )


def test_provider_request_rejects_a_micro_run_charge_above_the_micro_cap() -> None:
    with pytest.raises(ValueError, match="charge limit exceeds the approved micro-run cap"):
        ProviderRequest(
            provider_id="apify-linkedin",
            role_query_id="senior-product-manager",
            location_id="bengaluru",
            listing_limit=5,
            max_charge_usd=Decimal("0.11"),
        )


def test_apify_provider_rejects_an_unapproved_actor() -> None:
    with pytest.raises(ValueError, match="unsupported Apify Actor"):
        ApifyProvider("unapproved/actor")


def test_provider_http_client_uses_fixed_timeouts_and_disables_redirects() -> None:
    with create_provider_http_client() as client:
        assert client.timeout.connect == 10.0
        assert client.timeout.read == 90.0
        assert client.follow_redirects is False


def test_apify_linkedin_request_is_bounded_to_the_approved_https_actor_endpoint() -> None:
    prepared = ApifyProvider(APIFY_LINKEDIN_ACTOR).prepare(
        ProviderRequest(
            provider_id="apify-linkedin",
            role_query_id="senior-product-manager",
            location_id="bengaluru",
            listing_limit=5,
            max_charge_usd=Decimal("0.10"),
        )
    )

    assert prepared.url == (
        "https://api.apify.com/v2/acts/"
        "curious_coder~linkedin-jobs-scraper/run-sync-get-dataset-items"
    )
    assert prepared.params == {
        "format": "json",
        "limit": "5",
        "maxItems": "5",
        "maxTotalChargeUsd": "0.10",
    }
    assert prepared.json == {
        "keywords": "senior-product-manager",
        "location": "bengaluru",
        "limitPerSource": 5,
    }


def test_apify_linkedin_accepts_the_documented_india_subdomain_for_public_listing_urls() -> None:
    listing = ApifyProvider(APIFY_LINKEDIN_ACTOR)._parse_listing(
        {
            "id": "sanitized-linkedin-id",
            "link": "https://in.linkedin.com/jobs/view/1234567890?tracking=removed",
        },
        datetime.now(UTC),
    )

    assert listing.canonical_url == "https://in.linkedin.com/jobs/view/1234567890"


def test_apify_naukri_request_is_bounded_to_the_approved_https_actor_endpoint() -> None:
    prepared = ApifyProvider(APIFY_NAUKRI_ACTOR).prepare(
        ProviderRequest(
            provider_id="apify-naukri",
            role_query_id="senior-product-manager",
            location_id="bengaluru",
            listing_limit=5,
            max_charge_usd=Decimal("0.10"),
        )
    )

    assert prepared.url == (
        "https://api.apify.com/v2/acts/automation-lab~naukri-scraper/"
        "run-sync-get-dataset-items"
    )
    assert prepared.params == {
        "format": "json",
        "limit": "5",
        "maxItems": "5",
        "maxTotalChargeUsd": "0.10",
    }
    assert prepared.json == {
        "keyword": "senior-product-manager",
        "location": "bengaluru",
        "maxJobs": 5,
    }


def test_apify_glassdoor_request_is_bounded_to_the_approved_https_actor_endpoint() -> None:
    prepared = ApifyProvider(APIFY_GLASSDOOR_ACTOR).prepare(
        ProviderRequest(
            provider_id="apify-glassdoor",
            role_query_id="senior-product-manager",
            location_id="bengaluru",
            listing_limit=5,
            max_charge_usd=Decimal("0.10"),
        )
    )

    assert prepared.url == (
        "https://api.apify.com/v2/acts/valig~glassdoor-jobs-scraper/"
        "run-sync-get-dataset-items"
    )
    assert prepared.params == {
        "format": "json",
        "limit": "5",
        "maxItems": "5",
        "maxTotalChargeUsd": "0.10",
    }
    assert prepared.json == {
        "keywords": "senior-product-manager",
        "location": "bengaluru",
        "limit": 5,
    }


def test_jsearch_request_is_bounded_to_the_approved_https_search_endpoint() -> None:
    prepared = JSearchProvider().prepare(
        ProviderRequest(
            provider_id="jsearch",
            role_query_id="senior-product-manager",
            location_id="bengaluru",
            listing_limit=5,
        )
    )

    assert prepared.url == "https://jsearch.p.rapidapi.com/search-v2"
    assert prepared.params == {"query": "senior-product-manager in bengaluru"}
    assert prepared.json is None


def test_discovery_planning_rejects_the_retired_aggregator_pipeline(tmp_path: Path) -> None:
    profile = build_profile_v1()
    inputs = Phase1ActivationInputs(
        acceptance_receipt=Phase1AcceptanceReceiptSnapshot(
            id="acceptance-id",
            application_build="test-build",
            schema_revision="0002_phase1_contract",
            acceptance_suite_version="test-suite",
            acceptance_run_id="test-run",
            result_fingerprint="a" * 64,
            restore_high_water_mark=0,
            accepted_at="2026-08-26T00:00:00+00:00",
            fingerprint="b" * 64,
        ),
        readiness=Phase1ReadinessSnapshot(
            ready_for_phase_2=True,
            manifest_version="test-manifest",
            import_run_id="test-import",
            source_hashes={},
            active_profile_version=1,
            readiness_generation=1,
            authority_high_water_mark=1,
            restore_generation=0,
            fingerprint="c" * 64,
        ),
        profile=SearchProfileSnapshot(
            version_number=1,
            payload=profile,
            active_profile_generation=1,
            fingerprint="d" * 64,
        ),
    )

    with pytest.raises(ProviderConfigurationError, match="no approved official provider instances"):
        DiscoveryService(Phase2Settings(data_dir=tmp_path))._plans(inputs)


def test_approved_instance_uses_only_durable_approval_metadata() -> None:
    approval = Phase2ProviderInstanceApproval(
        id="approval-1",
        instance_id="employer-greenhouse-v1",
        provider_kind="greenhouse_public_board",
        employer_identity="Example Employer",
        hosts_json=["boards-api.greenhouse.io"],
        endpoint_url="https://boards-api.greenhouse.io/v1/boards/example/jobs?content=true",
        redirect_hosts_json=[],
        path_prefixes_json=["/v1/boards/example/jobs"],
        parser_version="greenhouse-public-v1",
        content_types_json=["application/json"],
        source_identifier="example",
        max_response_bytes=1_000_000,
        min_request_interval_seconds=30,
        enabled=True,
        actor="local-user",
        reason="approved boundary",
        phase2_activation_generation=1,
        phase2_restore_generation=0,
        approval_fingerprint="a" * 64,
    )

    instance = _approved_instance(approval)

    assert instance.instance_id == approval.instance_id
    assert instance.source_identifier == "example"
    assert instance.content_types == ("application/json",)
