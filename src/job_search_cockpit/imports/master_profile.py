import re
from datetime import date

from job_search_cockpit.config import SourceKind, SourceSpec
from job_search_cockpit.imports.grammar import (
    conservative_risks,
    evidence,
    mark_ambiguous_collisions,
    normalize_text,
    parse_period,
    semantic_anchor,
    slugify,
)
from job_search_cockpit.imports.types import CandidateClaim, ImportResult, MalformedSourceError
from job_search_cockpit.sources import OpenedSource, safe_open_source

_ALLOWED_SIMPLE_SECTIONS = {"contact", "education", "certifications", "languages"}


def _candidate(
    opened: OpenedSource,
    canonical_key: str,
    category: str,
    subject: str,
    display: str,
    locator: str,
    employer: str | None = None,
    period: tuple[date | None, date | None] = (None, None),
    family: str | None = None,
) -> CandidateClaim:
    return CandidateClaim(
        canonical_key=canonical_key,
        category=category,
        subject=subject,
        value={"text": normalize_text(display)},
        display_value=normalize_text(display),
        evidence=evidence(opened, locator, display),
        employer_key=employer,
        period_start=period[0],
        period_end=period[1],
        semantic_family=family or canonical_key,
        declared_risks=conservative_risks(category, canonical_key, display),
    )


class MasterProfileImporter:
    def read(self, spec: SourceSpec) -> ImportResult:
        if spec.kind is not SourceKind.MASTER_PROFILE:
            raise MalformedSourceError("The source manifest declares the wrong format.")
        opened = safe_open_source(spec)
        try:
            lines = opened.content.decode("utf-8").splitlines()
        except UnicodeDecodeError as error:
            raise MalformedSourceError("The master profile is not valid UTF-8.") from error

        claims: list[CandidateClaim] = []
        section = ""
        company = ""
        employer: str | None = None
        title = ""
        period: tuple[date | None, date | None] = (None, None)
        pending_experience: list[tuple[int, str]] = []
        for line_number, raw in enumerate(lines, start=1):
            line = raw.strip()
            if line.startswith("## "):
                section = slugify(line[3:])
                company = ""
                employer = None
                pending_experience.clear()
                continue
            if section == "professional-experience" and line.startswith("### "):
                heading = line[4:]
                parts = re.split(r"\s+[-\u2013\u2014]\s+", heading, maxsplit=1)
                if len(parts) != 2:
                    raise MalformedSourceError("An experience heading has no title.")
                company, title = map(normalize_text, parts)
                employer = slugify(company)
                period = (None, None)
                pending_experience = [(line_number, title)]
                continue
            if section == "professional-experience" and employer:
                if line.lower().startswith("dates:"):
                    dates = normalize_text(line.split(":", 1)[1])
                    period = parse_period(dates)
                    title_line, title_value = pending_experience.pop(0)
                    claims.append(
                        _candidate(
                            opened,
                            f"employment.{employer}.title",
                            "title",
                            company,
                            title_value,
                            f"line:{title_line}",
                            employer,
                            period,
                            f"employment.title.{employer}",
                        )
                    )
                    claims.append(
                        _candidate(
                            opened,
                            f"employment.{employer}.dates",
                            "dates",
                            company,
                            dates,
                            f"line:{line_number}",
                            employer,
                            period,
                            f"employment.dates.{employer}",
                        )
                    )
                    continue
                if line.startswith("- "):
                    statement = line[2:].strip()
                    anchor = semantic_anchor(statement)
                    family = f"employment.statement.{employer}.{anchor}"
                    if re.search(r"\b\d+\s+scrum teams?\b", statement, re.IGNORECASE):
                        family = f"team_scope.{employer}"
                    claims.append(
                        _candidate(
                            opened,
                            f"employment.{employer}.{anchor}",
                            "achievement",
                            company,
                            statement,
                            f"line:{line_number}",
                            employer,
                            period,
                            family,
                        )
                    )
                continue
            if section == "high-impact-metrics-proof-points" and line.startswith("- "):
                statement = line[2:].strip()
                anchor = semantic_anchor(statement)
                claims.append(
                    _candidate(
                        opened,
                        f"metric.{anchor}",
                        "achievement",
                        "Varun Nanduri",
                        statement,
                        f"line:{line_number}",
                        family=f"metric.{anchor}",
                    )
                )
                continue
            simple_section = section.rstrip("s")
            if section in _ALLOWED_SIMPLE_SECTIONS and line.startswith("- "):
                value = line[2:].strip()
                if section == "contact" and ":" in value:
                    label, display = value.split(":", 1)
                    canonical = f"contact.{slugify(label)}"
                    category = "contact"
                else:
                    display = value
                    canonical = f"{simple_section}.{semantic_anchor(value)}"
                    category = simple_section
                claims.append(
                    _candidate(
                        opened,
                        canonical,
                        category,
                        "Varun Nanduri",
                        display.strip(),
                        f"line:{line_number}",
                    )
                )
        if not claims:
            raise MalformedSourceError("The master profile has no recognized factual sections.")
        return ImportResult(spec.key, opened.content_hash, mark_ambiguous_collisions(claims))
