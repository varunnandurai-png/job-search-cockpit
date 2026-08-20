import re
import unicodedata
from dataclasses import replace
from datetime import date

from job_search_cockpit.facts.types import RiskFlag
from job_search_cockpit.imports.types import CandidateClaim, EvidenceRef
from job_search_cockpit.sources import OpenedSource

_MONTHS = {
    name: number
    for number, name in enumerate(
        (
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ),
        start=1,
    )
}
_MUTABLE_NUMBER = re.compile(
    r"(?i)(?:[$₹€£S]\s*)?\b\d[\d,.]*(?:\s*[-\u2013\u2014]\s*\d[\d,.]*)?"
    r"\s*(?:%|[KMB]\+?)?"
)
_PUNCTUATION = re.compile(r"[^a-z0-9]+")
_SPACE = re.compile(r"\s+")
_DATE_TOKENS = frozenset((*_MONTHS, "present"))


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).replace("\u2013", "-").replace("\u2014", "-")
    return _SPACE.sub(" ", normalized).strip()


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return _PUNCTUATION.sub("-", normalized).strip("-")


def semantic_anchor(value: str) -> str:
    without_numbers = _MUTABLE_NUMBER.sub(" ", normalize_text(value))
    tokens = [
        token
        for token in slugify(without_numbers).split("-")
        if token and token not in _DATE_TOKENS
    ]
    return "-".join(tokens) or "statement"


def parse_period(value: str) -> tuple[date | None, date | None]:
    normalized = normalize_text(value).lower()
    matches = re.findall(
        r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})",
        normalized,
    )
    if not matches:
        return None, None
    start_month, start_year = matches[0]
    start = date(int(start_year), _MONTHS[start_month], 1)
    if "present" in normalized or len(matches) == 1:
        return start, None
    end_month, end_year = matches[1]
    return start, date(int(end_year), _MONTHS[end_month], 1)


def evidence(opened: OpenedSource, locator: str, excerpt: str) -> EvidenceRef:
    return EvidenceRef(
        source_key=opened.spec.key,
        source_path=opened.spec.path,
        source_hash=opened.content_hash,
        locator=locator,
        excerpt=normalize_text(excerpt),
    )


def conservative_risks(category: str, canonical_key: str, value: str) -> frozenset[RiskFlag]:
    lowered = value.lower()
    private_markers = (
        "confidential",
        "private",
        "client",
        "vendor",
        "compensation",
        "salary",
    )
    is_money = bool(re.search(r"(?:[$₹€£]|\b(?:usd|inr|sgd)\b)\s*\d", value, re.IGNORECASE))
    if category == "contact" or canonical_key.startswith("contact."):
        return frozenset({RiskFlag.POTENTIALLY_CONFIDENTIAL})
    if is_money or any(marker in lowered for marker in private_markers):
        return frozenset({RiskFlag.POTENTIALLY_CONFIDENTIAL})
    return frozenset()


def mark_ambiguous_collisions(claims: list[CandidateClaim]) -> tuple[CandidateClaim, ...]:
    by_key: dict[str, list[CandidateClaim]] = {}
    for claim in claims:
        by_key.setdefault(claim.canonical_key, []).append(claim)
    result: list[CandidateClaim] = []
    for claim in claims:
        siblings = by_key[claim.canonical_key]
        distinct_values = {sibling.display_value for sibling in siblings}
        if len(distinct_values) > 1:
            claim = replace(claim, declared_risks=claim.declared_risks | {RiskFlag.CONFLICT})
        if any(
            existing.canonical_key == claim.canonical_key
            and existing.display_value == claim.display_value
            for existing in result
        ):
            continue
        result.append(claim)
    return tuple(result)
