from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ProviderListing:
    """Inert public listing data returned only by an approved official adapter."""

    provider_listing_id: str
    canonical_url: str
    title: str
    employer_name: str
    locations: tuple[str, ...]
    posted_at: datetime | None
    public_description: str
    compensation_text: str | None
    retrieved_at: datetime
