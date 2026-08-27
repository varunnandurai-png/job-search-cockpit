from collections.abc import Callable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from ipaddress import IPv4Address, IPv6Address
from urllib.parse import SplitResult, parse_qsl, urljoin, urlsplit

from job_search_cockpit.phase2.provider_instances import ApprovedProviderInstance

ResolvedAddress = IPv4Address | IPv6Address
Resolver = Callable[[str], tuple[ResolvedAddress, ...]]

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_SENSITIVE_QUERY_NAMES = frozenset(
    {"access_token", "api_key", "authorization", "key", "password", "secret", "token"}
)


class ProviderContainmentError(RuntimeError):
    """Raised when an official-source request crosses a containment boundary."""


@dataclass(frozen=True, slots=True)
class ContainedOfficialRequest:
    url: str
    hostname: str
    addresses: tuple[ResolvedAddress, ...]
    max_response_bytes: int
    content_types: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InertOfficialResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes
    connected_address: ResolvedAddress


Executor = Callable[[ContainedOfficialRequest], InertOfficialResponse]
Revalidator = Callable[[], object]


class ContainedOfficialTransport:
    """Validates each target before delegating to a pinned request executor."""

    def __init__(
        self, *, resolver: Resolver, executor: Executor, revalidate: Revalidator
    ) -> None:
        self._resolver = resolver
        self._executor = executor
        self._revalidate = revalidate

    def fetch(
        self, instance: ApprovedProviderInstance, url: str
    ) -> InertOfficialResponse:
        current_url = url
        for redirect_count in range(3):
            self._revalidate()
            request = self._request_for(instance, current_url, allow_redirect=redirect_count > 0)
            self._revalidate()
            response = self._executor(request)
            self._revalidate()
            self._validate_response(request, response)
            if response.status_code not in _REDIRECT_STATUSES:
                if not 200 <= response.status_code < 300:
                    raise ProviderContainmentError(
                        "official provider returned an unexpected status"
                    )
                return response
            if redirect_count == 2:
                raise ProviderContainmentError("official provider exceeded the redirect cap")
            location = _header_value(response.headers, "location")
            if not location:
                raise ProviderContainmentError("official provider redirect lacks a location")
            current_url = urljoin(current_url, location)
        raise AssertionError("redirect loop must return or raise")

    def _request_for(
        self, instance: ApprovedProviderInstance, url: str, *, allow_redirect: bool
    ) -> ContainedOfficialRequest:
        parts = _validate_url(instance, url, allow_redirect=allow_redirect)
        hostname = parts.hostname
        if hostname is None:
            raise ProviderContainmentError("official provider URL lacks a hostname")
        addresses = self._resolver(hostname)
        if not addresses or any(not _is_public_address(address) for address in addresses):
            raise ProviderContainmentError(
                "official provider host must resolve only to public addresses"
            )
        return ContainedOfficialRequest(
            url=url,
            hostname=hostname,
            addresses=addresses,
            max_response_bytes=instance.max_response_bytes,
            content_types=instance.content_types,
        )

    @staticmethod
    def _validate_response(
        request: ContainedOfficialRequest, response: InertOfficialResponse
    ) -> None:
        if response.connected_address not in request.addresses:
            raise ProviderContainmentError(
                "official provider connected outside the resolved address set"
            )
        if len(response.body) > request.max_response_bytes:
            raise ProviderContainmentError("official provider response exceeds the approved size")
        content_type = _header_value(response.headers, "content-type").split(";", 1)[0].strip()
        if content_type not in request.content_types:
            raise ProviderContainmentError(
                "official provider response has an unexpected content type"
            )


def response_fingerprint(response: InertOfficialResponse) -> str:
    return sha256(response.body).hexdigest()


def _validate_url(
    instance: ApprovedProviderInstance, url: str, *, allow_redirect: bool
) -> SplitResult:
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as error:
        raise ProviderContainmentError("official provider URL has an invalid port") from error
    allowed_hosts = set(instance.hosts)
    if allow_redirect:
        allowed_hosts.update(instance.redirect_hosts)
    hostname = parts.hostname.lower() if parts.hostname is not None else None
    if (
        parts.scheme != "https"
        or parts.username is not None
        or parts.password is not None
        or port not in {None, 443}
        or parts.fragment
        or hostname not in allowed_hosts
        or not any(parts.path.startswith(prefix) for prefix in instance.path_prefixes)
        or _has_sensitive_query_parameter(parts.query)
    ):
        raise ProviderContainmentError(
            "official provider URL is outside the approved containment policy"
        )
    return parts


def _has_sensitive_query_parameter(query: str) -> bool:
    return any(
        name.lower() in _SENSITIVE_QUERY_NAMES
        for name, _value in parse_qsl(query, keep_blank_values=True)
    )


def _is_public_address(address: ResolvedAddress) -> bool:
    if isinstance(address, IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped.is_global
    return address.is_global


def _header_value(headers: Mapping[str, str], name: str) -> str:
    return next((value for key, value in headers.items() if key.lower() == name), "")


__all__ = [
    "ContainedOfficialRequest",
    "ContainedOfficialTransport",
    "InertOfficialResponse",
    "ProviderContainmentError",
    "response_fingerprint",
]
