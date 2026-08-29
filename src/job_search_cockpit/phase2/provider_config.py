import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from job_search_cockpit.phase2.config import Phase2Settings


class ProviderConfigurationError(ValueError):
    """Raised when provider access is not configured safely."""


_ALLOWED_ENV_KEYS = frozenset({"APIFY_API_TOKEN", "JSEARCH_API_KEY"})
_MAX_DOTENV_BYTES = 8_192


def read_provider_env_file(phase2_settings: Phase2Settings) -> dict[str, str]:
    """Read the provider-only dotenv file derived from trusted application settings."""
    path = phase2_settings.data_dir / ".env"
    _validate_dotenv_path(path)
    return _read_provider_env_file(path)


def _read_provider_env_file(path: Path) -> dict[str, str]:
    """Parse a validated provider dotenv file without executing dotenv syntax."""
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
        phase2_settings: Phase2Settings | None = None,
    ) -> "ProviderCredentials":
        source = os.environ if environment is None else environment
        dotenv = read_provider_env_file(phase2_settings) if phase2_settings is not None else {}
        apify_token = source.get("APIFY_API_TOKEN") or dotenv.get("APIFY_API_TOKEN", "")
        jsearch_key = source.get("JSEARCH_API_KEY") or dotenv.get("JSEARCH_API_KEY", "")
        if not apify_token:
            raise ProviderConfigurationError("Apify credentials are unavailable.")
        if not jsearch_key:
            raise ProviderConfigurationError("JSearch credentials are unavailable.")
        return cls(apify_token=apify_token, jsearch_key=jsearch_key)


def _validate_dotenv_path(path: Path) -> None:
    if path.name != ".env":
        raise ProviderConfigurationError("Provider dotenv file must be named .env.")
    if path.is_symlink():
        raise ProviderConfigurationError("Provider dotenv file must not be a symlink.")
    try:
        path.resolve(strict=True)
        file_status = path.stat()
    except OSError as error:
        raise ProviderConfigurationError("Provider environment file is unavailable.") from error
    if not stat.S_ISREG(file_status.st_mode):
        raise ProviderConfigurationError("Provider dotenv path must be a regular file.")
    if file_status.st_mode & 0o077:
        raise ProviderConfigurationError("Provider dotenv file permissions must be owner-only.")
    if file_status.st_size > _MAX_DOTENV_BYTES:
        raise ProviderConfigurationError("Provider dotenv file exceeds the size limit.")


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
