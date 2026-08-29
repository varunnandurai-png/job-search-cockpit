from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from ipaddress import ip_address
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

import httpx

from job_search_cockpit.phase2.discovery_types import (
    PROVIDER_FAILURE_CODES,
    ProviderListing,
    ProviderRequest,
)
from job_search_cockpit.phase2.provider_config import ProviderCredentials

APIFY_LINKEDIN_ACTOR = "curious_coder/linkedin-jobs-scraper"
APIFY_NAUKRI_ACTOR = "automation-lab/naukri-scraper"
APIFY_GLASSDOOR_ACTOR = "valig/glassdoor-jobs-scraper"
JSEARCH_HOST = "jsearch.p.rapidapi.com"
JSEARCH_SEARCH_ENDPOINT = "/search"

_APIFY_ACTORS = frozenset(
    {APIFY_LINKEDIN_ACTOR, APIFY_NAUKRI_ACTOR, APIFY_GLASSDOOR_ACTOR}
)
_APIFY_BASE_URL = "https://api.apify.com/v2/acts"
_APIFY_PROVIDER_IDS = {
    APIFY_LINKEDIN_ACTOR: "apify-linkedin",
    APIFY_NAUKRI_ACTOR: "apify-naukri",
    APIFY_GLASSDOOR_ACTOR: "apify-glassdoor",
}
_APIFY_LISTING_HOSTS = {
    APIFY_LINKEDIN_ACTOR: frozenset({"www.linkedin.com", "in.linkedin.com"}),
    APIFY_NAUKRI_ACTOR: frozenset({"www.naukri.com"}),
    APIFY_GLASSDOOR_ACTOR: frozenset({"www.glassdoor.com"}),
}
class ProviderResponseError(RuntimeError):
    """Raised with a bounded provider failure code and safe detail."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        if code not in PROVIDER_FAILURE_CODES:
            raise ValueError("unsupported provider failure code")
        self.code = code
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True, slots=True)
class _PreparedProviderRequest:
    url: str
    params: dict[str, str]
    json: dict[str, object] | None


def create_provider_http_client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(90.0, connect=10.0),
        follow_redirects=False,
        transport=httpx.HTTPTransport(retries=0),
    )


class ApifyProvider:
    def __init__(self, actor_id: str) -> None:
        if actor_id not in _APIFY_ACTORS:
            raise ValueError("unsupported Apify Actor")
        self.actor_id = actor_id

    def prepare(self, request: ProviderRequest) -> _PreparedProviderRequest:
        if request.provider_id != _APIFY_PROVIDER_IDS[self.actor_id]:
            raise ValueError("provider request does not match the selected Apify Actor")
        if request.max_charge_usd is None:
            raise ValueError("Apify requests require an approved charge limit")

        if self.actor_id == APIFY_LINKEDIN_ACTOR:
            payload: dict[str, object] = {
                "keywords": request.role_query_id,
                "location": request.location_id,
                "limitPerSource": request.listing_limit,
            }
        elif self.actor_id == APIFY_NAUKRI_ACTOR:
            payload = {
                "keyword": request.role_query_id,
                "location": request.location_id,
                "maxJobs": request.listing_limit,
            }
        else:
            payload = {
                "keywords": request.role_query_id,
                "location": request.location_id,
                "limit": request.listing_limit,
            }
        actor_path = self.actor_id.replace("/", "~", 1)
        return _PreparedProviderRequest(
            url=f"{_APIFY_BASE_URL}/{actor_path}/run-sync-get-dataset-items",
            params={
                "format": "json",
                "limit": str(request.listing_limit),
                "maxItems": str(request.listing_limit),
                "maxTotalChargeUsd": _decimal_parameter(request.max_charge_usd),
            },
            json=payload,
        )

    def fetch(
        self,
        request: ProviderRequest,
        credentials: ProviderCredentials,
        client: httpx.Client,
    ) -> tuple[ProviderListing, ...]:
        prepared = self.prepare(request)
        _require_bounded_client(client)
        try:
            response = client.post(
                prepared.url,
                params=prepared.params,
                json=prepared.json,
                headers={"Authorization": f"Bearer {credentials.apify_token}"},
            )
            response.raise_for_status()
        except httpx.TimeoutException as error:
            raise ProviderResponseError("timeout") from error
        except httpx.HTTPStatusError as error:
            raise _http_failure(error.response.status_code) from error
        except httpx.HTTPError as error:
            raise ProviderResponseError("provider_unavailable") from error
        return self.parse(response, request.listing_limit, datetime.now(UTC))

    def parse(
        self,
        response: httpx.Response,
        listing_limit: int,
        retrieved_at: datetime,
    ) -> tuple[ProviderListing, ...]:
        payload = _response_json(response)
        if not isinstance(payload, list):
            raise ProviderResponseError("schema_mismatch")
        _require_listing_limit(payload, listing_limit)
        return tuple(self._parse_listing(item, retrieved_at) for item in payload)

    def _parse_listing(self, item: object, retrieved_at: datetime) -> ProviderListing:
        if not isinstance(item, dict):
            raise ProviderResponseError("invalid_listing")
        if self.actor_id == APIFY_LINKEDIN_ACTOR:
            return ProviderListing(
                provider_listing_id=_required_text(item, "id"),
                canonical_url=_canonical_listing_url(
                    _required_text(item, "link"), _APIFY_LISTING_HOSTS[self.actor_id]
                ),
                title=_optional_text(item, "title"),
                employer_name=_optional_text(item, "companyName"),
                locations=_locations(item.get("location")),
                posted_at=_optional_datetime(item.get("postedAt")),
                public_description=_optional_text(item, "descriptionText"),
                compensation_text=_compensation_text(item.get("salaryInfo")),
                retrieved_at=retrieved_at,
            )
        if self.actor_id == APIFY_NAUKRI_ACTOR:
            return ProviderListing(
                provider_listing_id=_required_text(item, "jobId"),
                canonical_url=_canonical_listing_url(
                    _required_text(item, "jobUrl"), _APIFY_LISTING_HOSTS[self.actor_id]
                ),
                title=_optional_text(item, "title"),
                employer_name=_optional_text(item, "companyName"),
                locations=_locations(item.get("location")),
                posted_at=_optional_datetime(item.get("postedDate")),
                public_description=_optional_text(item, "jobDescription"),
                compensation_text=_optional_nullable_text(item.get("salary")),
                retrieved_at=retrieved_at,
            )
        return ProviderListing(
            provider_listing_id=_required_identifier(item, "id"),
            canonical_url=_canonical_listing_url(
                _required_text(item, "url"), _APIFY_LISTING_HOSTS[self.actor_id]
            ),
            title=_optional_text(item, "title"),
            employer_name=_nested_optional_text(item, "employer", "name"),
            locations=_locations(_nested_value(item, "location", "name")),
            posted_at=None,
            public_description=_optional_text(item, "description"),
            compensation_text=_compensation_text(item.get("pay")),
            retrieved_at=retrieved_at,
        )


class JSearchProvider:
    def prepare(self, request: ProviderRequest) -> _PreparedProviderRequest:
        if request.provider_id != "jsearch":
            raise ValueError("provider request does not match JSearch")
        return _PreparedProviderRequest(
            url=f"https://{JSEARCH_HOST}{JSEARCH_SEARCH_ENDPOINT}",
            params={
                "query": f"{request.role_query_id} in {request.location_id}",
                "page": "1",
                "num_pages": "1",
            },
            json=None,
        )

    def fetch(
        self,
        request: ProviderRequest,
        credentials: ProviderCredentials,
        client: httpx.Client,
    ) -> tuple[ProviderListing, ...]:
        prepared = self.prepare(request)
        _require_bounded_client(client)
        try:
            response = client.get(
                prepared.url,
                params=prepared.params,
                headers={
                    "X-RapidAPI-Key": credentials.jsearch_key,
                    "X-RapidAPI-Host": JSEARCH_HOST,
                },
            )
            response.raise_for_status()
        except httpx.TimeoutException as error:
            raise ProviderResponseError("timeout") from error
        except httpx.HTTPStatusError as error:
            raise _http_failure(error.response.status_code) from error
        except httpx.HTTPError as error:
            raise ProviderResponseError("provider_unavailable") from error
        return self.parse(response, request.listing_limit, datetime.now(UTC))

    def parse(
        self,
        response: httpx.Response,
        listing_limit: int,
        retrieved_at: datetime,
    ) -> tuple[ProviderListing, ...]:
        payload = _response_json(response)
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ProviderResponseError("schema_mismatch")
        jobs = payload["data"]
        _require_listing_limit(jobs, listing_limit)
        return tuple(self._parse_listing(item, retrieved_at) for item in jobs)

    def _parse_listing(self, item: object, retrieved_at: datetime) -> ProviderListing:
        if not isinstance(item, dict):
            raise ProviderResponseError("invalid_listing")
        return ProviderListing(
            provider_listing_id=_required_text(item, "job_id"),
            canonical_url=_canonical_public_url(_required_text(item, "job_apply_link")),
            title=_optional_text(item, "job_title"),
            employer_name=_optional_text(item, "employer_name"),
            locations=_locations(item.get("job_location")),
            posted_at=_optional_datetime(item.get("job_posted_at_datetime_utc")),
            public_description=_optional_text(item, "job_description"),
            compensation_text=None,
            retrieved_at=retrieved_at,
        )


def _decimal_parameter(value: Decimal) -> str:
    return format(value, "f")


def _require_bounded_client(client: httpx.Client) -> None:
    if client.follow_redirects or client.timeout.connect != 10.0 or client.timeout.read != 90.0:
        raise ValueError("provider HTTP client is not configured safely")
    if _http_transport_retry_count(client) != 0:
        raise ValueError("provider HTTP client must disable retries")


def _http_transport_retry_count(client: httpx.Client) -> int:
    """Read httpx's retry setting in one boundary until it has a public accessor."""
    transport = client._transport
    if not isinstance(transport, httpx.HTTPTransport):
        return 0
    return transport._pool._retries


def _http_failure(status_code: int) -> ProviderResponseError:
    if status_code in {401, 403}:
        return ProviderResponseError("authentication_failed")
    if status_code in {402, 429}:
        return ProviderResponseError("quota_or_cost_limit")
    return ProviderResponseError("provider_unavailable")


def _response_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError as error:
        raise ProviderResponseError("schema_mismatch") from error


def _require_listing_limit(items: list[object], listing_limit: int) -> None:
    if listing_limit < 1:
        raise ValueError("listing limit must be positive")
    if len(items) > listing_limit:
        raise ProviderResponseError("schema_mismatch", "listing limit exceeded")


def _required_text(item: dict[object, object], field_name: str) -> str:
    value = item.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ProviderResponseError("invalid_listing", "stable identifier or public URL is missing")
    return value.strip()


def _required_identifier(item: dict[object, object], field_name: str) -> str:
    value = item.get(field_name)
    if isinstance(value, int) and value >= 0:
        return str(value)
    return _required_text(item, field_name)


def _optional_text(item: dict[object, object], field_name: str) -> str:
    value = item.get(field_name)
    return value.strip() if isinstance(value, str) else ""


def _optional_nullable_text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _nested_value(item: dict[object, object], parent: str, field_name: str) -> object:
    value = item.get(parent)
    return value.get(field_name) if isinstance(value, dict) else None


def _nested_optional_text(item: dict[object, object], parent: str, field_name: str) -> str:
    value = _nested_value(item, parent, field_name)
    return value.strip() if isinstance(value, str) else ""


def _locations(value: object) -> tuple[str, ...]:
    if isinstance(value, str) and value.strip():
        return (value.strip(),)
    if isinstance(value, list):
        return tuple(part.strip() for part in value if isinstance(part, str) and part.strip())
    return ()


def _optional_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _compensation_text(value: object) -> str | None:
    if isinstance(value, str):
        return _optional_nullable_text(value)
    if isinstance(value, list):
        parts = [part.strip() for part in value if isinstance(part, str) and part.strip()]
        return " - ".join(parts) or None
    return None


def _canonical_listing_url(value: str, approved_hosts: frozenset[str]) -> str:
    parsed = _safe_urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in approved_hosts
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or not parsed.path
    ):
        raise ProviderResponseError("invalid_listing", "public listing URL is not approved")
    assert parsed.hostname is not None
    return urlunsplit(("https", parsed.hostname, parsed.path, "", ""))


def _canonical_public_url(value: str) -> str:
    parsed = _safe_urlsplit(value)
    hostname = parsed.hostname
    if (
        parsed.scheme != "https"
        or hostname is None
        or not _is_public_hostname(hostname)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or not parsed.path
    ):
        raise ProviderResponseError("invalid_listing", "public listing URL is invalid")
    return urlunsplit(("https", hostname, parsed.path, parsed.query, ""))


def _safe_urlsplit(value: str) -> SplitResult:
    try:
        parsed = urlsplit(value)
        _ = parsed.port
        return parsed
    except ValueError as error:
        raise ProviderResponseError("invalid_listing", "public listing URL is invalid") from error


def _is_public_hostname(hostname: str) -> bool:
    try:
        return ip_address(hostname).is_global
    except ValueError:
        return "." in hostname and not hostname.endswith(
            (".example", ".internal", ".invalid", ".local", ".localhost", ".test")
        )


__all__ = [
    "APIFY_GLASSDOOR_ACTOR",
    "APIFY_LINKEDIN_ACTOR",
    "APIFY_NAUKRI_ACTOR",
    "JSEARCH_HOST",
    "JSEARCH_SEARCH_ENDPOINT",
    "ApifyProvider",
    "JSearchProvider",
    "ProviderResponseError",
    "create_provider_http_client",
]
