from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path

import pytest

from job_search_cockpit.phase2.discovery_types import ProviderRequest
from job_search_cockpit.phase2.provider_config import (
    ProviderConfigurationError,
    ProviderCredentials,
    read_provider_env_file,
)
from job_search_cockpit.phase2.providers import (
    APIFY_LINKEDIN_ACTOR,
    APIFY_NAUKRI_ACTOR,
    ApifyProvider,
    create_provider_http_client,
)


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
        assert client.timeout.read == 30.0
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
        "https://api.apify.com/v2/acts/crawlerbros~naukri-scraper/"
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
        "maxItems": 5,
    }
