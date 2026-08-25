from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from job_search_cockpit.phase2.discovery_types import ProviderListing, ProviderRequest
from job_search_cockpit.phase2.provider_config import ProviderCredentials

APIFY_LINKEDIN_ACTOR = "curious_coder/linkedin-jobs-scraper"
APIFY_NAUKRI_ACTOR = "crawlerbros/naukri-scraper"

_APIFY_ACTORS = frozenset({APIFY_LINKEDIN_ACTOR, APIFY_NAUKRI_ACTOR})
_APIFY_BASE_URL = "https://api.apify.com/v2/acts"
_APIFY_PROVIDER_IDS = {
    APIFY_LINKEDIN_ACTOR: "apify-linkedin",
    APIFY_NAUKRI_ACTOR: "apify-naukri",
}
_APIFY_LISTING_HOSTS = {
    APIFY_LINKEDIN_ACTOR: "www.linkedin.com",
    APIFY_NAUKRI_ACTOR: "www.naukri.com",
}


class ProviderResponseError(RuntimeError):
    """Raised when a provider response cannot be accepted safely."""


@dataclass(frozen=True, slots=True)
class _PreparedProviderRequest:
    url: str
    params: dict[str, str]
    json: dict[str, object]


def create_provider_http_client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(30.0, connect=10.0),
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

        actor_path = self.actor_id.replace("/", "~", 1)
        if self.actor_id == APIFY_LINKEDIN_ACTOR:
            payload: dict[str, object] = {
                "keywords": request.role_query_id,
                "location": request.location_id,
                "limitPerSource": request.listing_limit,
            }
        else:
            payload = {
                "keyword": request.role_query_id,
                "location": request.location_id,
                "maxItems": request.listing_limit,
            }
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
            payload: Any = response.json()
        except (httpx.HTTPError, ValueError):
            raise ProviderResponseError("Apify provider request failed.") from None

        if not isinstance(payload, list):
            raise ProviderResponseError("Apify provider returned an invalid response.")
        if len(payload) > request.listing_limit:
            raise ProviderResponseError("Apify provider exceeded the requested listing limit.")

        retrieved_at = datetime.now(UTC)
        return tuple(self._parse_listing(item, retrieved_at) for item in payload)

    def _parse_listing(self, item: object, retrieved_at: datetime) -> ProviderListing:
        if not isinstance(item, dict):
            raise ProviderResponseError("Apify provider returned an invalid listing.")

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
        return ProviderListing(
            provider_listing_id=_required_text(item, "id"),
            canonical_url=_canonical_listing_url(
                _required_text(item, "url"), _APIFY_LISTING_HOSTS[self.actor_id]
            ),
            title=_optional_text(item, "title"),
            employer_name=_optional_text(item, "companyName"),
            locations=_locations(item.get("location")),
            posted_at=_optional_datetime(item.get("postedAt")),
            public_description=_optional_text(item, "description"),
            compensation_text=_optional_nullable_text(item.get("salary")),
            retrieved_at=retrieved_at,
        )


def _decimal_parameter(value: Decimal) -> str:
    return format(value, "f")


def _require_bounded_client(client: httpx.Client) -> None:
    if (
        client.follow_redirects
        or client.timeout.connect != 10.0
        or client.timeout.read != 30.0
    ):
        raise ValueError("provider HTTP client is not configured safely")


def _required_text(item: dict[object, object], field_name: str) -> str:
    value = item.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ProviderResponseError("Provider listing lacks a stable identifier or public URL.")
    return value.strip()


def _optional_text(item: dict[object, object], field_name: str) -> str:
    value = item.get(field_name)
    return value.strip() if isinstance(value, str) else ""


def _optional_nullable_text(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


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


def _canonical_listing_url(value: str, approved_host: str) -> str:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ProviderResponseError(
            "Provider listing lacks a stable identifier or public URL."
        ) from None
    if (
        parsed.scheme != "https"
        or parsed.hostname != approved_host
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or not parsed.path
    ):
        raise ProviderResponseError("Provider listing lacks a stable identifier or public URL.")
    return urlunsplit(("https", approved_host, parsed.path, "", ""))


__all__ = [
    "APIFY_LINKEDIN_ACTOR",
    "APIFY_NAUKRI_ACTOR",
    "ApifyProvider",
    "ProviderResponseError",
    "create_provider_http_client",
]
