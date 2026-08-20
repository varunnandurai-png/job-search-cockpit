from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict


@dataclass(frozen=True, slots=True)
class MoneyFloor:
    currency: str
    amount: int
    basis: str


class SearchProfilePayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    eligible_roles: tuple[str, ...]
    priority_domains: tuple[str, ...]
    excluded_role_patterns: tuple[str, ...]
    locations: tuple[str, ...]
    location_allocation: dict[str, int]
    role_difficulty_allocation: dict[str, int]
    sponsorship_requirements: dict[str, str]
    compensation_floors: dict[str, MoneyFloor]
    excluded_employers: tuple[str, ...]
    notice_period_days: int
    preferred_level: str
    title_rules: tuple[str, ...]
    profile_change_requires_reason: bool
    profile_change_confirmation: str


def build_profile_v1() -> SearchProfilePayload:
    return SearchProfilePayload(
        eligible_roles=(
            "Senior Product Manager",
            "Lead Product Manager — individual contributor",
            "Selected Principal Product Manager — individual contributor",
            "Applied AI Product Manager with domain overlap",
            "Senior Technical Product Manager — platforms, APIs, integrations, data, "
            "fintech, lending, commerce, or fulfilment",
        ),
        priority_domains=(
            "Digital lending, mortgage, and home buying",
            "Banking, fintech, risk, fraud, and relevant payments",
            "E-commerce, fulfilment, last mile, and omnichannel",
            "Subscriptions, billing, and commerce platforms",
            "Platforms, APIs, and partner integrations",
            "Data, analytics, operational products, and decision support",
            "Applied AI with existing domain overlap",
        ),
        excluded_role_patterns=(
            "Associate Product Manager and junior product roles",
            "Generic Business Analyst",
            "Delivery-only Product Owner without exceptional scope and compensation",
            "Program Manager without product ownership",
            "Director roles dependent on formal people management",
            "Deep AI infrastructure or foundation-model platforms without domain overlap",
            "General Singapore roles without strong domain match or sponsorship",
            "Substantial level downgrade",
        ),
        locations=("Hyderabad", "Bengaluru", "Singapore"),
        location_allocation={"Hyderabad": 40, "Bengaluru": 45, "Singapore": 15},
        role_difficulty_allocation={"direct_fit": 50, "stretch": 35, "aspirational": 15},
        sponsorship_requirements={"Singapore": "Employer-sponsored Employment Pass"},
        compensation_floors={
            "Hyderabad": MoneyFloor("INR", 4_600_000, "annual_total"),
            "Bengaluru": MoneyFloor("INR", 4_800_000, "annual_total"),
            "Singapore": MoneyFloor("SGD", 120_000, "annual_base"),
        },
        excluded_employers=("JPMorganChase",),
        notice_period_days=60,
        preferred_level="Senior individual contributor",
        title_rules=(
            "A lateral title is acceptable only for genuine AI product scope",
            "A substantial level downgrade is not acceptable",
        ),
        profile_change_requires_reason=True,
        profile_change_confirmation="CREATE NEW SEARCH PROFILE VERSION",
    )
