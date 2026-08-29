import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path


class ProviderConfigurationError(ValueError):
    """Raised when provider access is not configured safely."""


_ALLOWED_ENV_KEYS = frozenset({"APIFY_API_TOKEN", "JSEARCH_API_KEY"})


def read_provider_env_file(path: Path) -> dict[str, str]:
    """Read allowlisted provider settings without executing dotenv syntax."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ProviderConfigurationError("Provider environment file is unavailable.") from error

    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ProviderConfigurationError(
                f"Provider environment file has an invalid line {line_number}."
            )
        key, value = (part.strip() for part in line.split("=", 1))
        if key not in _ALLOWED_ENV_KEYS:
            raise ProviderConfigurationError(
                "Provider environment file contains an unsupported key."
            )
        if key in values:
            raise ProviderConfigurationError("Provider environment file contains a duplicate key.")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if not value:
            raise ProviderConfigurationError("Provider environment file contains an empty value.")
        values[key] = value
    return values


@dataclass(frozen=True, slots=True, repr=False)
class ProviderCredentials:
    apify_token: str = field(repr=False)
    jsearch_key: str = field(repr=False)

    def __repr__(self) -> str:
        return "<>"

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
        *,
        dotenv_path: Path | None = None,
    ) -> "ProviderCredentials":
        source = os.environ if environment is None else environment
        dotenv = read_provider_env_file(dotenv_path) if dotenv_path is not None else {}
        apify_token = source.get("APIFY_API_TOKEN") or dotenv.get("APIFY_API_TOKEN", "")
        jsearch_key = source.get("JSEARCH_API_KEY") or dotenv.get("JSEARCH_API_KEY", "")
        if not apify_token:
            raise ProviderConfigurationError("Apify credentials are unavailable.")
        if not jsearch_key:
            raise ProviderConfigurationError("JSearch credentials are unavailable.")
        return cls(apify_token=apify_token, jsearch_key=jsearch_key)


@dataclass(frozen=True, slots=True)
class ProviderLimits:
    linkedin_listing_limit: int = 40
    naukri_listing_limit: int = 25
    glassdoor_listing_limit: int = 25
    jsearch_listing_limit: int = 25
    max_apify_charge_usd: Decimal = Decimal("0.50")
    micro_listing_limit: int = 5
    micro_apify_charge_usd: Decimal = Decimal("0.10")

    @classmethod
    def listing_limit_for(cls, provider_id: str) -> int:
        limits = cls()
        if provider_id == "apify-linkedin":
            return limits.linkedin_listing_limit
        if provider_id == "apify-naukri":
            return limits.naukri_listing_limit
        if provider_id == "apify-glassdoor":
            return limits.glassdoor_listing_limit
        if provider_id == "jsearch":
            return limits.jsearch_listing_limit
        raise ValueError("unsupported provider")


__all__ = [
    "ProviderConfigurationError",
    "ProviderCredentials",
    "ProviderLimits",
    "read_provider_env_file",
]
