from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from ipaddress import ip_address
from urllib.parse import parse_qsl, urlsplit

_SENSITIVE_QUERY_NAMES = frozenset(
    {"access_token", "api_key", "authorization", "key", "password", "secret", "token"}
)


class OfficialProviderKind(StrEnum):
    GREENHOUSE_PUBLIC_BOARD = "greenhouse_public_board"
    LEVER_PUBLIC_BOARD = "lever_public_board"
    OFFICIAL_PAGE_READ_ONLY = "official_page_read_only"
    MANUAL_OFFICIAL_URL_READ_ONLY = "manual_official_url_read_only"


class ProviderInstanceUnavailable(RuntimeError):
    """Raised when no approved official provider instance can be used."""


@dataclass(frozen=True, slots=True)
class ApprovedProviderInstance:
    instance_id: str
    kind: OfficialProviderKind
    employer_identity: str
    hosts: tuple[str, ...]
    endpoint_url: str
    redirect_hosts: tuple[str, ...]
    path_prefixes: tuple[str, ...]
    parser_version: str
    max_response_bytes: int
    min_request_interval_seconds: int
    content_types: tuple[str, ...] = ("application/json",)
    source_identifier: str | None = None

    def __post_init__(self) -> None:
        if not self.instance_id.strip() or not self.employer_identity.strip():
            raise ValueError("provider instance and employer identity are required")
        _validate_hosts(self.hosts)
        _validate_hosts(self.redirect_hosts)
        if not self.path_prefixes or len(set(self.path_prefixes)) != len(self.path_prefixes):
            raise ValueError("provider instance requires unique path prefixes")
        if any(not prefix.startswith("/") for prefix in self.path_prefixes):
            raise ValueError("provider instance path prefixes must be absolute")
        if not self.parser_version.strip():
            raise ValueError("provider instance requires a parser version")
        if self.source_identifier is not None and not _is_source_identifier(
            self.source_identifier
        ):
            raise ValueError("provider instance source identifier is invalid")
        if not self.content_types or len(set(self.content_types)) != len(self.content_types):
            raise ValueError("provider instance requires exact content types")
        if any(not _is_exact_content_type(content_type) for content_type in self.content_types):
            raise ValueError("provider instance requires exact content types")
        if not 1 <= self.max_response_bytes <= 2_000_000:
            raise ValueError("provider response size is outside the approved bounds")
        if not 1 <= self.min_request_interval_seconds <= 86_400:
            raise ValueError("provider request interval is outside the approved bounds")

        endpoint = urlsplit(self.endpoint_url)
        if (
            endpoint.scheme != "https"
            or endpoint.username is not None
            or endpoint.password is not None
            or endpoint.port not in {None, 443}
            or _has_sensitive_query_parameter(endpoint.query)
            or endpoint.fragment
            or endpoint.hostname is None
            or endpoint.hostname.lower() not in self.hosts
            or not any(endpoint.path.startswith(prefix) for prefix in self.path_prefixes)
        ):
            raise ValueError("provider instance requires an exact HTTPS host and endpoint")


@dataclass(frozen=True, slots=True)
class ProviderInstanceApproval:
    instance: ApprovedProviderInstance
    approval_fingerprint: str
    enabled: bool
    actor: str
    reason: str
    approved_at: datetime

    def __post_init__(self) -> None:
        if (
            len(self.approval_fingerprint) != 64
            or any(character not in "0123456789abcdef" for character in self.approval_fingerprint)
        ):
            raise ValueError("provider instance approval fingerprint must be a SHA-256 digest")
        if not self.actor.strip() or not self.reason.strip():
            raise ValueError("provider instance approval actor and reason are required")
        if self.approved_at.tzinfo is None:
            raise ValueError("provider instance approval time must be timezone-aware")


def _validate_hosts(hosts: tuple[str, ...]) -> None:
    if len(set(hosts)) != len(hosts) or any(not _is_exact_host(host) for host in hosts):
        raise ValueError("provider instance requires exact HTTPS hosts")


def _is_exact_host(host: str) -> bool:
    if not host or host != host.lower() or "*" in host or ":" in host or "/" in host:
        return False
    try:
        ip_address(host)
    except ValueError:
        return "." in host and all(
            part and part.replace("-", "").isalnum() for part in host.split(".")
        )
    return False


def _is_exact_content_type(content_type: str) -> bool:
    if (
        content_type != content_type.lower()
        or content_type.count("/") != 1
        or "*" in content_type
    ):
        return False
    type_name, subtype = content_type.split("/", 1)
    token_characters = frozenset("!#$%&'*+-.^_`|~0123456789abcdefghijklmnopqrstuvwxyz")
    return bool(type_name) and bool(subtype) and all(
        character in token_characters for character in type_name + subtype
    )


def _is_source_identifier(value: str) -> bool:
    return bool(value) and all(character.isalnum() or character in "-_" for character in value)


def _has_sensitive_query_parameter(query: str) -> bool:
    return any(
        name.lower() in _SENSITIVE_QUERY_NAMES
        for name, _value in parse_qsl(query, keep_blank_values=True)
    )


__all__ = [
    "ApprovedProviderInstance",
    "OfficialProviderKind",
    "ProviderInstanceApproval",
    "ProviderInstanceUnavailable",
]
