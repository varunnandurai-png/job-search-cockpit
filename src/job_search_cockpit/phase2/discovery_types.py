from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from job_search_cockpit.phase2.provider_config import ProviderLimits

_APIFY_PROVIDER_IDS = frozenset(
    {"apify-linkedin", "apify-naukri", "apify-glassdoor"}
)
ProviderFailureCode = Literal[
    "authentication_failed",
    "quota_or_cost_limit",
    "timeout",
    "provider_unavailable",
    "schema_mismatch",
    "invalid_listing",
]
PROVIDER_FAILURE_CODES: frozenset[ProviderFailureCode] = frozenset(
    {
        "authentication_failed",
        "quota_or_cost_limit",
        "timeout",
        "provider_unavailable",
        "schema_mismatch",
        "invalid_listing",
    }
)


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    provider_id: str
    role_query_id: str
    location_id: str
    listing_limit: int
    max_charge_usd: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.role_query_id.strip() or not self.location_id.strip():
            raise ValueError("role query and location are required")
        if self.listing_limit < 1:
            raise ValueError("listing limit must be positive")
        if self.listing_limit > ProviderLimits.listing_limit_for(self.provider_id):
            raise ValueError("listing limit exceeds the approved pilot cap")
        if self.provider_id in _APIFY_PROVIDER_IDS:
            if self.max_charge_usd is None:
                raise ValueError("Apify requests require an approved charge limit")
            if not Decimal("0") < self.max_charge_usd <= ProviderLimits().max_apify_charge_usd:
                raise ValueError("Apify charge limit is outside the approved pilot cap")
            if (
                self.listing_limit <= ProviderLimits().micro_listing_limit
                and self.max_charge_usd > ProviderLimits().micro_apify_charge_usd
            ):
                raise ValueError("Apify charge limit exceeds the approved micro-run cap")
        elif self.max_charge_usd is not None:
            raise ValueError("only Apify requests may set a charge limit")


@dataclass(frozen=True, slots=True)
class ProviderListing:
    provider_listing_id: str
    canonical_url: str
    title: str
    employer_name: str
    locations: tuple[str, ...]
    posted_at: datetime | None
    public_description: str
    compensation_text: str | None
    retrieved_at: datetime


@dataclass(frozen=True, slots=True)
class ProviderOutcome:
    provider_id: str
    listings: tuple[ProviderListing, ...] = ()
    failure_code: str | None = None

    def __post_init__(self) -> None:
        if self.failure_code is not None and self.failure_code not in PROVIDER_FAILURE_CODES:
            raise ValueError("provider outcome has an unsupported failure code")


__all__ = [
    "PROVIDER_FAILURE_CODES",
    "ProviderFailureCode",
    "ProviderListing",
    "ProviderOutcome",
    "ProviderRequest",
]
