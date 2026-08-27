from dataclasses import dataclass
from typing import Protocol

from job_search_cockpit.phase2.discovery_types import ProviderListing
from job_search_cockpit.phase2.provider_instances import (
    ApprovedProviderInstance,
    OfficialProviderKind,
    ProviderInstanceUnavailable,
)
from job_search_cockpit.phase2.safe_transport import InertOfficialResponse


class OfficialProviderAdapter(Protocol):
    kind: OfficialProviderKind

    def endpoint_for(self, instance: ApprovedProviderInstance) -> str: ...


class OfficialProviderParser(Protocol):
    def __call__(
        self, instance: ApprovedProviderInstance, response: InertOfficialResponse
    ) -> tuple[ProviderListing, ...]: ...


class OfficialProviderTransport(Protocol):
    def fetch(
        self, instance: ApprovedProviderInstance, url: str
    ) -> InertOfficialResponse: ...


class GreenhousePublicBoardAdapter:
    kind = OfficialProviderKind.GREENHOUSE_PUBLIC_BOARD

    def endpoint_for(self, instance: ApprovedProviderInstance) -> str:
        if instance.kind != self.kind or not instance.source_identifier:
            raise ProviderInstanceUnavailable("official provider instance is not registered")
        endpoint = (
            "https://boards-api.greenhouse.io/v1/boards/"
            f"{instance.source_identifier}/jobs?content=true"
        )
        if endpoint != instance.endpoint_url:
            raise ProviderInstanceUnavailable("official provider endpoint is not approved")
        return endpoint


class LeverPublicBoardAdapter:
    kind = OfficialProviderKind.LEVER_PUBLIC_BOARD

    def endpoint_for(self, instance: ApprovedProviderInstance) -> str:
        if instance.kind != self.kind or not instance.source_identifier:
            raise ProviderInstanceUnavailable("official provider instance is not registered")
        endpoint = f"https://api.lever.co/v0/postings/{instance.source_identifier}?mode=json"
        if endpoint != instance.endpoint_url:
            raise ProviderInstanceUnavailable("official provider endpoint is not approved")
        return endpoint


class OfficialPageReadOnlyAdapter:
    kind = OfficialProviderKind.OFFICIAL_PAGE_READ_ONLY

    def endpoint_for(self, instance: ApprovedProviderInstance) -> str:
        if instance.kind != self.kind:
            raise ProviderInstanceUnavailable("official provider instance is not registered")
        return instance.endpoint_url


class ManualOfficialUrlReadOnlyAdapter:
    kind = OfficialProviderKind.MANUAL_OFFICIAL_URL_READ_ONLY

    def endpoint_for(self, instance: ApprovedProviderInstance) -> str:
        if instance.kind != self.kind:
            raise ProviderInstanceUnavailable("official provider instance is not registered")
        return instance.endpoint_url


@dataclass(frozen=True, slots=True)
class OfficialProviderAdapterRegistry:
    adapters: tuple[OfficialProviderAdapter, ...] = ()
    parsers: tuple[tuple[str, str, OfficialProviderParser], ...] = ()

    @classmethod
    def empty(cls) -> "OfficialProviderAdapterRegistry":
        return cls()

    @classmethod
    def with_public_board_adapters(cls) -> "OfficialProviderAdapterRegistry":
        return cls((GreenhousePublicBoardAdapter(), LeverPublicBoardAdapter()))

    @classmethod
    def with_direct_source_adapters(cls) -> "OfficialProviderAdapterRegistry":
        return cls(
            (
                GreenhousePublicBoardAdapter(),
                LeverPublicBoardAdapter(),
                OfficialPageReadOnlyAdapter(),
                ManualOfficialUrlReadOnlyAdapter(),
            )
        )

    def with_parser(
        self, instance_id: str, parser_version: str, parser: OfficialProviderParser
    ) -> "OfficialProviderAdapterRegistry":
        if not instance_id.strip() or any(
            existing_id == instance_id for existing_id, _version, _parser in self.parsers
        ):
            raise ValueError("official provider parser instance ID must be unique")
        if not parser_version.strip():
            raise ValueError("official provider parser version is required")
        return OfficialProviderAdapterRegistry(
            self.adapters, (*self.parsers, (instance_id, parser_version, parser))
        )

    def adapter_for(self, kind: OfficialProviderKind) -> OfficialProviderAdapter:
        for adapter in self.adapters:
            if adapter.kind == kind:
                return adapter
        raise ProviderInstanceUnavailable("official provider adapter is not registered")

    def fetch(
        self, instance: ApprovedProviderInstance, transport: OfficialProviderTransport
    ) -> tuple[ProviderListing, ...]:
        adapter = self.adapter_for(instance.kind)
        parser = self._parser_for(instance)
        response = transport.fetch(instance, adapter.endpoint_for(instance))
        return parser(instance, response)

    def _parser_for(self, instance: ApprovedProviderInstance) -> OfficialProviderParser:
        for registered_id, registered_version, parser in self.parsers:
            if registered_id == instance.instance_id:
                if registered_version != instance.parser_version:
                    raise ProviderInstanceUnavailable(
                        "official provider parser version is not approved"
                    )
                return parser
        raise ProviderInstanceUnavailable("official provider parser is not registered")


__all__ = [
    "GreenhousePublicBoardAdapter",
    "LeverPublicBoardAdapter",
    "ManualOfficialUrlReadOnlyAdapter",
    "OfficialPageReadOnlyAdapter",
    "OfficialProviderAdapter",
    "OfficialProviderAdapterRegistry",
    "OfficialProviderParser",
    "OfficialProviderTransport",
]
