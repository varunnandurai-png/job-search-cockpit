from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from job_search_cockpit.phase2.discovery_types import (
    ProviderListing,
    ProviderOutcome,
    ProviderRequest,
)
from job_search_cockpit.phase2.provider_config import (
    ProviderConfigurationError,
    ProviderCredentials,
    ProviderLimits,
    read_provider_env_file,
)
from job_search_cockpit.phase2.providers import (
    APIFY_GLASSDOOR_ACTOR,
    APIFY_LINKEDIN_ACTOR,
    APIFY_NAUKRI_ACTOR,
    JSEARCH_HOST,
    ApifyProvider,
    JSearchProvider,
    ProviderResponseError,
    _require_bounded_client,
    create_provider_http_client,
)

NOW = datetime(2026, 8, 29, 0, 0, tzinfo=UTC)


def test_credentials_are_redacted_and_env_rejects_unknown_keys(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("APIFY_API_TOKEN=a\nJSEARCH_API_KEY=j\n", encoding="utf-8")
    env.chmod(0o600)

    credentials = ProviderCredentials.from_environment(
        {}, dotenv_path=env, approved_dotenv_path=env
    )

    assert "a" not in repr(credentials)
    assert "j" not in repr(credentials)

    env.write_text("HOME=x\n", encoding="utf-8")
    with pytest.raises(ProviderConfigurationError, match="unsupported key"):
        read_provider_env_file(env)


def test_micro_apify_request_rejects_cost_above_ten_cents() -> None:
    with pytest.raises(ValueError, match="micro-run cap"):
        ProviderRequest(
            "apify-linkedin",
            "Senior Product Manager",
            "Hyderabad",
            5,
            Decimal("0.11"),
        )


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("APIFY_API_TOKEN=\n", "empty value"),
        ("APIFY_API_TOKEN=one\nAPIFY_API_TOKEN=two\n", "duplicate key"),
        ("not a dotenv assignment\n", "invalid line"),
    ],
)
def test_provider_env_file_rejects_invalid_values(
    contents: str, message: str, tmp_path: Path
) -> None:
    env = tmp_path / ".env"
    env.write_text(contents, encoding="utf-8")

    with pytest.raises(ProviderConfigurationError, match=message):
        read_provider_env_file(env)


def test_credentials_fail_closed_and_remain_immutable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    monkeypatch.delenv("JSEARCH_API_KEY", raising=False)

    with pytest.raises(ProviderConfigurationError, match="Apify credentials are unavailable"):
        ProviderCredentials.from_environment()

    credentials = ProviderCredentials("apify", "jsearch")
    with pytest.raises(FrozenInstanceError):
        credentials.apify_token = "changed"  # type: ignore[misc]


def test_credentials_require_an_exact_private_dotenv_anchor(tmp_path: Path) -> None:
    env = tmp_path / "provider-data" / ".env"
    env.parent.mkdir()
    env.write_text("APIFY_API_TOKEN=a\nJSEARCH_API_KEY=j\n", encoding="utf-8")
    env.chmod(0o600)
    different = tmp_path / "other-data" / ".env"
    different.parent.mkdir()
    different.write_text("APIFY_API_TOKEN=a\nJSEARCH_API_KEY=j\n", encoding="utf-8")
    different.chmod(0o600)

    with pytest.raises(ProviderConfigurationError, match="approved dotenv path"):
        ProviderCredentials.from_environment({}, dotenv_path=env)
    with pytest.raises(ProviderConfigurationError, match="approved dotenv path"):
        ProviderCredentials.from_environment(
            {}, dotenv_path=env, approved_dotenv_path=different
        )

    assert ProviderCredentials.from_environment(
        {}, dotenv_path=env, approved_dotenv_path=env
    ) == ProviderCredentials("a", "j")


def test_credentials_reject_an_untrusted_dotenv_file_shape(tmp_path: Path) -> None:
    wrong_name = tmp_path / "provider.env"
    wrong_name.write_text("APIFY_API_TOKEN=a\nJSEARCH_API_KEY=j\n", encoding="utf-8")
    wrong_name.chmod(0o600)
    with pytest.raises(ProviderConfigurationError, match=r"named .env"):
        ProviderCredentials.from_environment(
            {}, dotenv_path=wrong_name, approved_dotenv_path=wrong_name
        )

    loose = tmp_path / ".env"
    loose.write_text("APIFY_API_TOKEN=a\nJSEARCH_API_KEY=j\n", encoding="utf-8")
    loose.chmod(0o644)
    with pytest.raises(ProviderConfigurationError, match="owner-only"):
        ProviderCredentials.from_environment({}, dotenv_path=loose, approved_dotenv_path=loose)

    directory = tmp_path / "directory" / ".env"
    directory.parent.mkdir()
    directory.mkdir()
    with pytest.raises(ProviderConfigurationError, match="regular file"):
        ProviderCredentials.from_environment(
            {}, dotenv_path=directory, approved_dotenv_path=directory
        )

    link_parent = tmp_path / "linked"
    link_parent.mkdir()
    link = link_parent / ".env"
    link.symlink_to(loose)
    with pytest.raises(ProviderConfigurationError, match="symlink"):
        ProviderCredentials.from_environment({}, dotenv_path=link, approved_dotenv_path=link)


def test_credentials_reject_a_dotenv_file_over_the_bounded_size(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("APIFY_API_TOKEN=a\nJSEARCH_API_KEY=j\n" + "#" * 8193, encoding="utf-8")
    env.chmod(0o600)

    with pytest.raises(ProviderConfigurationError, match="size limit"):
        ProviderCredentials.from_environment({}, dotenv_path=env, approved_dotenv_path=env)


@pytest.mark.parametrize(
    ("provider_id", "listing_limit", "max_charge_usd", "message"),
    [
        ("apify-linkedin", 41, Decimal("0.10"), "pilot cap"),
        ("apify-naukri", 26, Decimal("0.10"), "pilot cap"),
        ("apify-glassdoor", 26, Decimal("0.10"), "pilot cap"),
        ("jsearch", 26, None, "pilot cap"),
        ("unknown", 1, None, "unsupported provider"),
        ("apify-linkedin", 1, Decimal("0"), "charge limit"),
        ("apify-linkedin", 1, Decimal("0.51"), "charge limit"),
    ],
)
def test_provider_request_rejects_out_of_policy_values(
    provider_id: str,
    listing_limit: int,
    max_charge_usd: Decimal | None,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        ProviderRequest(provider_id, "role", "place", listing_limit, max_charge_usd)


def test_provider_request_requires_query_and_location() -> None:
    with pytest.raises(ValueError, match="role query and location"):
        ProviderRequest("jsearch", " ", "place", 1)
    with pytest.raises(ValueError, match="role query and location"):
        ProviderRequest("jsearch", "role", " ", 1)


def test_provider_limits_have_the_approved_values() -> None:
    assert ProviderLimits() == ProviderLimits(
        linkedin_listing_limit=40,
        naukri_listing_limit=25,
        glassdoor_listing_limit=25,
        jsearch_listing_limit=25,
        max_apify_charge_usd=Decimal("0.50"),
        micro_listing_limit=5,
        micro_apify_charge_usd=Decimal("0.10"),
    )


def test_provider_outcome_rejects_unbounded_failure_codes() -> None:
    with pytest.raises(ValueError, match="failure code"):
        ProviderOutcome(provider_id="jsearch", failure_code="arbitrary_failure")

    assert ProviderOutcome(provider_id="jsearch", failure_code="timeout").failure_code == "timeout"


def test_provider_http_client_uses_fixed_timeouts_without_redirects() -> None:
    with create_provider_http_client() as client:
        assert client.timeout.connect == 10.0
        assert client.timeout.read == 90.0
        assert client.follow_redirects is False


def test_provider_rejects_an_http_transport_configured_with_retries() -> None:
    client = httpx.Client(
        transport=httpx.HTTPTransport(retries=1),
        timeout=httpx.Timeout(90.0, connect=10.0),
        follow_redirects=False,
    )

    with pytest.raises(ValueError, match="retries"):
        _require_bounded_client(client)


@pytest.mark.parametrize(
    ("actor_id", "provider_id", "payload"),
    [
        (
            APIFY_LINKEDIN_ACTOR,
            "apify-linkedin",
            {"keywords": "Senior Product Manager", "location": "Hyderabad", "limitPerSource": 5},
        ),
        (
            APIFY_NAUKRI_ACTOR,
            "apify-naukri",
            {"keyword": "Senior Product Manager", "location": "Hyderabad", "maxJobs": 5},
        ),
        (
            APIFY_GLASSDOOR_ACTOR,
            "apify-glassdoor",
            {"keywords": "Senior Product Manager", "location": "Hyderabad", "limit": 5},
        ),
    ],
)
def test_apify_request_uses_the_actor_specific_https_contract(
    actor_id: str, provider_id: str, payload: dict[str, object]
) -> None:
    prepared = ApifyProvider(actor_id).prepare(
        ProviderRequest(provider_id, "Senior Product Manager", "Hyderabad", 5, Decimal("0.10"))
    )

    assert prepared.url == (
        "https://api.apify.com/v2/acts/"
        f"{actor_id.replace('/', '~', 1)}/run-sync-get-dataset-items"
    )
    assert prepared.params == {
        "format": "json",
        "limit": "5",
        "maxItems": "5",
        "maxTotalChargeUsd": "0.10",
    }
    assert prepared.json == payload


def test_apify_micro_request_contains_item_and_charge_caps() -> None:
    prepared = ApifyProvider(APIFY_LINKEDIN_ACTOR).prepare(
        ProviderRequest("apify-linkedin", "Senior Product Manager", "Hyderabad", 5, Decimal("0.10"))
    )

    assert prepared.params["maxItems"] == "5"
    assert prepared.params["maxTotalChargeUsd"] == "0.10"
    assert prepared.url.startswith("https://api.apify.com/v2/acts/")


def test_jsearch_request_uses_only_the_current_v3_https_endpoint() -> None:
    prepared = JSearchProvider().prepare(
        ProviderRequest("jsearch", "Senior Product Manager", "Hyderabad", 5)
    )

    assert prepared.url == "https://jsearch.p.rapidapi.com/search"
    assert prepared.params == {
        "query": "Senior Product Manager in Hyderabad",
        "page": "1",
        "num_pages": "1",
    }
    assert prepared.json is None


def test_apify_parse_rejects_excess_results_and_bad_response_shapes() -> None:
    provider = ApifyProvider(APIFY_LINKEDIN_ACTOR)
    response = httpx.Response(200, json=[_linkedin_job(index) for index in range(6)])

    with pytest.raises(ProviderResponseError, match="listing limit"):
        provider.parse(response, listing_limit=5, retrieved_at=NOW)
    with pytest.raises(ProviderResponseError, match="schema_mismatch"):
        provider.parse(httpx.Response(200, json={"items": []}), listing_limit=5, retrieved_at=NOW)


def test_apify_parse_canonicalizes_only_approved_public_listing_hosts() -> None:
    listing = ApifyProvider(APIFY_LINKEDIN_ACTOR).parse(
        httpx.Response(
            200,
            json=[
                _linkedin_job(
                    1,
                    link="https://in.linkedin.com/jobs/view/123?tracking=discarded#fragment",
                )
            ],
        ),
        listing_limit=5,
        retrieved_at=NOW,
    )[0]

    assert listing.provider_listing_id == "linkedin-1"
    assert listing.canonical_url == "https://in.linkedin.com/jobs/view/123"
    with pytest.raises(ProviderResponseError, match="invalid_listing"):
        ApifyProvider(APIFY_LINKEDIN_ACTOR).parse(
            httpx.Response(200, json=[_linkedin_job(1, link="https://evil.invalid/job")]),
            listing_limit=5,
            retrieved_at=NOW,
        )


def test_jsearch_rejects_more_jobs_than_requested() -> None:
    response = httpx.Response(200, json={"data": [_job(index) for index in range(6)]})

    with pytest.raises(ProviderResponseError, match="listing limit"):
        JSearchProvider().parse(response, listing_limit=5, retrieved_at=NOW)


def test_jsearch_accepts_only_the_current_v3_data_list_envelope() -> None:
    provider = JSearchProvider()
    listings = provider.parse(
        httpx.Response(200, json={"data": [_job(1)]}), listing_limit=5, retrieved_at=NOW
    )

    assert listings == (
        ProviderListing(
            provider_listing_id="jsearch-1",
            canonical_url="https://careers.acme.com/jobs/1?source=public",
            title="Senior Product Manager",
            employer_name="Acme",
            locations=("Hyderabad",),
            posted_at=NOW,
            public_description="Public job description",
            compensation_text=None,
            retrieved_at=NOW,
        ),
    )
    with pytest.raises(ProviderResponseError, match="schema_mismatch"):
        provider.parse(
            httpx.Response(200, json={"data": {"jobs": [_job(1)]}}),
            listing_limit=5,
            retrieved_at=NOW,
        )


def test_jsearch_rejects_missing_stable_ids_and_non_public_listing_urls() -> None:
    provider = JSearchProvider()

    with pytest.raises(ProviderResponseError, match="invalid_listing"):
        provider.parse(
            httpx.Response(200, json={"data": [{**_job(1), "job_id": " "}]}),
            listing_limit=5,
            retrieved_at=NOW,
        )
    with pytest.raises(ProviderResponseError, match="invalid_listing"):
        provider.parse(
            httpx.Response(200, json={"data": [{**_job(1), "job_apply_link": "http://127.0.0.1/"}]}),
            listing_limit=5,
            retrieved_at=NOW,
        )
    with pytest.raises(ProviderResponseError, match="invalid_listing"):
        provider.parse(
            httpx.Response(
                200,
                json={"data": [{**_job(1), "job_apply_link": "https://careers.acme.com:bad/job"}]},
            ),
            listing_limit=5,
            retrieved_at=NOW,
        )


@pytest.mark.parametrize(
    ("status_code", "code"),
    [(401, "authentication_failed"), (429, "quota_or_cost_limit"), (503, "provider_unavailable")],
)
def test_fetch_maps_http_failures_to_bounded_codes(status_code: int, code: str) -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(status_code, request=request)),
        timeout=httpx.Timeout(90.0, connect=10.0),
        follow_redirects=False,
    )
    request = ProviderRequest("jsearch", "role", "place", 1)

    with pytest.raises(ProviderResponseError, match=f"^{code}$"):
        JSearchProvider().fetch(request, ProviderCredentials("a", "j"), client)


def test_fetch_maps_transport_timeouts_to_the_bounded_timeout_code() -> None:
    def raise_timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timeout", request=request)

    client = httpx.Client(
        transport=httpx.MockTransport(raise_timeout),
        timeout=httpx.Timeout(90.0, connect=10.0),
        follow_redirects=False,
    )

    with pytest.raises(ProviderResponseError, match=r"^timeout$"):
        JSearchProvider().fetch(
            ProviderRequest("jsearch", "role", "place", 1),
            ProviderCredentials("a", "j"),
            client,
        )


def test_fetch_constructs_authentication_headers_only_for_the_outbound_request() -> None:
    seen_headers: dict[str, str] = {}

    def respond(request: httpx.Request) -> httpx.Response:
        seen_headers.update(request.headers)
        return httpx.Response(200, json={"data": []}, request=request)

    client = httpx.Client(
        transport=httpx.MockTransport(respond),
        timeout=httpx.Timeout(90.0, connect=10.0),
        follow_redirects=False,
    )

    assert JSearchProvider().fetch(
        ProviderRequest("jsearch", "role", "place", 1), ProviderCredentials("a", "j"), client
    ) == ()
    assert seen_headers["x-rapidapi-key"] == "j"
    assert seen_headers["x-rapidapi-host"] == JSEARCH_HOST


def _linkedin_job(index: int, *, link: str | None = None) -> dict[str, object]:
    return {
        "id": f"linkedin-{index}",
        "link": link or f"https://www.linkedin.com/jobs/view/{index}",
        "title": "Senior Product Manager",
        "companyName": "Acme",
        "location": "Hyderabad",
        "postedAt": "2026-08-29T00:00:00Z",
        "descriptionText": "Public job description",
    }


def _job(index: int) -> dict[str, object]:
    return {
        "job_id": f"jsearch-{index}",
        "job_apply_link": f"https://careers.acme.com/jobs/{index}?source=public#fragment",
        "job_title": "Senior Product Manager",
        "employer_name": "Acme",
        "job_location": "Hyderabad",
        "job_posted_at_datetime_utc": "2026-08-29T00:00:00Z",
        "job_description": "Public job description",
    }
