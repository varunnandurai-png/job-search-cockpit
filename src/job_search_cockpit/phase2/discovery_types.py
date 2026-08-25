from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from job_search_cockpit.phase2.provider_config import ProviderLimits


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
        if self.max_charge_usd is not None and not (
            Decimal("0") < self.max_charge_usd <= ProviderLimits().max_apify_charge_usd
        ):
            raise ValueError("Apify charge limit is outside the approved pilot cap")


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


__all__ = ["ProviderListing", "ProviderRequest"]
