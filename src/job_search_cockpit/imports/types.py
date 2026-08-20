from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

from job_search_cockpit.config import SourceSpec
from job_search_cockpit.facts.types import RiskFlag
from job_search_cockpit.search_profile.catalog import SearchProfilePayload


class MalformedSourceError(ValueError):
    """Raised when a curated source cannot be parsed as its declared format."""


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    source_key: str
    source_path: Path
    source_hash: str
    locator: str
    excerpt: str


@dataclass(frozen=True, slots=True)
class CandidateClaim:
    canonical_key: str
    category: str
    subject: str
    value: dict[str, object]
    display_value: str
    evidence: EvidenceRef
    employer_key: str | None
    period_start: date | None
    period_end: date | None
    semantic_family: str
    declared_risks: frozenset[RiskFlag] = frozenset()


@dataclass(frozen=True, slots=True)
class ImportResult:
    source_key: str
    source_hash: str
    claims: tuple[CandidateClaim, ...]
    search_profile: SearchProfilePayload | None = None
    warnings: tuple[str, ...] = ()


class SourceImporter(Protocol):
    def read(self, spec: SourceSpec) -> ImportResult: ...
