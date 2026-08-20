import importlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def one(items: Iterable[Any], **attributes: object) -> Any:
    matches = [
        item
        for item in items
        if all(getattr(item, name) == value for name, value in attributes.items())
    ]
    if len(matches) != 1:
        raise AssertionError(f"Expected one match for {attributes}, found {len(matches)}")
    return matches[0]


@dataclass(slots=True)
class FixedClock:
    current: datetime = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)
    monotonic_value: float = 1_000.0

    def now(self) -> datetime:
        return self.current

    def monotonic_now(self) -> float:
        return self.monotonic_value

    def advance(self, *, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)
        self.monotonic_value += seconds


def _symbol(module: str, name: str) -> Any:
    return getattr(importlib.import_module(module), name)


def MoneyFloor(*args: object, **kwargs: object) -> Any:
    return _symbol("job_search_cockpit.search_profile.catalog", "MoneyFloor")(*args, **kwargs)


def candidate(canonical_key: str, display_value: str, **overrides: object) -> Any:
    evidence_type = _symbol("job_search_cockpit.imports.types", "EvidenceRef")
    candidate_type = _symbol("job_search_cockpit.imports.types", "CandidateClaim")
    values: dict[str, object] = {
        "canonical_key": canonical_key,
        "category": "achievement",
        "subject": "Fixture employer",
        "value": {"text": display_value},
        "display_value": display_value,
        "evidence": evidence_type(
            source_key="fixture",
            source_path=Path("/tmp/sanitized-fixture.md"),
            source_hash="0" * 64,
            locator="fixture:1",
            excerpt="Sanitized fixture excerpt",
        ),
        "employer_key": "fixture-employer",
        "period_start": None,
        "period_end": None,
        "semantic_family": canonical_key,
    }
    values.update(overrides)
    return candidate_type(**values)


def changed_profile() -> Any:
    profile = _symbol("job_search_cockpit.search_profile.catalog", "build_profile_v1")()
    return profile.model_copy(update={"notice_period_days": 30})


def load_golden_profile_v1() -> dict[str, object]:
    path = Path(__file__).parents[1] / "fixtures" / "golden_profile_v1.json"
    return json.loads(path.read_text(encoding="utf-8"))


def ordinary_claim() -> Any:
    return candidate("skills.sql", "SQL", category="skill", subject="Varun")


def conflicting_claims() -> Sequence[Any]:
    return (
        candidate("profile.product_years", "6 years"),
        candidate("profile.product_years", "8 years", source_key="second"),
    )


def confidential_claim() -> Any:
    risks = _symbol("job_search_cockpit.facts.types", "RiskFlag")
    return candidate(
        "contact.email",
        "person@example.test",
        category="contact",
        subject="Varun",
        employer_key=None,
        declared_risks=frozenset({risks.POTENTIALLY_CONFIDENTIAL}),
    )
