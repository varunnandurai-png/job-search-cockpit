import re

from job_search_cockpit.config import SourceKind, SourceSpec
from job_search_cockpit.imports.grammar import conservative_risks, evidence, normalize_text
from job_search_cockpit.imports.types import CandidateClaim, ImportResult, MalformedSourceError
from job_search_cockpit.search_profile.catalog import build_profile_v1
from job_search_cockpit.sources import safe_open_source

_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


class AssessmentImporter:
    def read(self, spec: SourceSpec) -> ImportResult:
        if spec.kind is not SourceKind.ASSESSMENT:
            raise MalformedSourceError("The source manifest declares the wrong format.")
        opened = safe_open_source(spec)
        try:
            text = opened.content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise MalformedSourceError("The assessment is not valid UTF-8.") from error
        match = re.search(
            r"approximately\s+\*\*(one|two|three|four|five|six|seven|eight|nine|ten)\s+years "
            r"of direct product ownership\*\*",
            text,
            re.IGNORECASE,
        )
        claims: list[CandidateClaim] = []
        if match:
            word = match.group(1).lower()
            display = normalize_text(match.group(0).replace("**", ""))
            canonical = "profile.product_years"
            claims.append(
                CandidateClaim(
                    canonical_key=canonical,
                    category="experience",
                    subject="Varun Nanduri",
                    value={"value": _NUMBER_WORDS[word], "qualifier": "approximately"},
                    display_value=display,
                    evidence=evidence(opened, f"offset:{match.start()}", display),
                    employer_key=None,
                    period_start=None,
                    period_end=None,
                    semantic_family=canonical,
                    declared_risks=conservative_risks("experience", canonical, display),
                )
            )
        if "Recommended search allocation" not in text:
            raise MalformedSourceError("The assessment has no recognized search-profile section.")
        return ImportResult(
            spec.key,
            opened.content_hash,
            tuple(claims),
            search_profile=build_profile_v1(),
        )
