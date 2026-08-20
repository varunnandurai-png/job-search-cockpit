import json
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


def _claim(
    *,
    opened: OpenedSource,
    canonical_key: str,
    category: str,
    subject: str,
    value: object,
    display_value: str,
    locator: str,
    employer_key: str | None = None,
    period: tuple[date | None, date | None] = (None, None),
    semantic_family: str | None = None,
) -> CandidateClaim:
    return CandidateClaim(
        canonical_key=canonical_key,
        category=category,
        subject=subject,
        value={"value": value},
        display_value=normalize_text(display_value),
        evidence=evidence(opened, locator, display_value),
        employer_key=employer_key,
        period_start=period[0],
        period_end=period[1],
        semantic_family=semantic_family or canonical_key,
        declared_risks=conservative_risks(category, canonical_key, display_value),
    )


class ProfileJsonImporter:
    def read(self, spec: SourceSpec) -> ImportResult:
        if spec.kind is not SourceKind.PROFILE_JSON:
            raise MalformedSourceError("The source manifest declares the wrong format.")
        opened = safe_open_source(spec)
        try:
            payload = json.loads(opened.content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise MalformedSourceError("The profile JSON is malformed.") from error
        if not isinstance(payload, dict):
            raise MalformedSourceError("The profile JSON root must be an object.")

        claims: list[CandidateClaim] = []
        contact = payload.get("contact", {})
        if not isinstance(contact, dict):
            raise MalformedSourceError("The contact section must be an object.")
        for key, value in contact.items():
            if isinstance(value, str):
                claims.append(
                    _claim(
                        opened=opened,
                        canonical_key=f"contact.{slugify(str(key))}",
                        category="contact",
                        subject="Varun Nanduri",
                        value=value,
                        display_value=value,
                        locator=f"$.contact.{key}",
                    )
                )

        scalar_claims = (
            ("summary", "profile.summary", "summary"),
            ("years_experience", "profile.total_years", "experience"),
            ("pm_years", "profile.product_years", "experience"),
        )
        for field, canonical_key, category in scalar_claims:
            if field in payload and isinstance(payload[field], str | int | float):
                value = payload[field]
                display = str(value)
                claims.append(
                    _claim(
                        opened=opened,
                        canonical_key=canonical_key,
                        category=category,
                        subject="Varun Nanduri",
                        value=value,
                        display_value=display,
                        locator=f"$.{field}",
                        semantic_family=canonical_key,
                    )
                )

        experiences = payload.get("experience", [])
        if not isinstance(experiences, list):
            raise MalformedSourceError("The experience section must be a list.")
        for index, item in enumerate(experiences):
            if not isinstance(item, dict) or not isinstance(item.get("company"), str):
                raise MalformedSourceError("Each experience entry must name a company.")
            company = normalize_text(item["company"])
            employer = slugify(company)
            dates_text = str(item.get("dates", ""))
            period = parse_period(dates_text)
            for field, category in (
                ("title", "title"),
                ("dates", "dates"),
                ("location", "location"),
            ):
                value = item.get(field)
                if isinstance(value, str) and value.strip():
                    claims.append(
                        _claim(
                            opened=opened,
                            canonical_key=f"employment.{employer}.{field}",
                            category=category,
                            subject=company,
                            value=value,
                            display_value=value,
                            locator=f"$.experience[{index}].{field}",
                            employer_key=employer,
                            period=period,
                            semantic_family=f"employment.{field}.{employer}",
                        )
                    )
            bullets = item.get("bullets", [])
            if not isinstance(bullets, list):
                raise MalformedSourceError("Experience bullets must be a list.")
            for bullet_index, bullet in enumerate(bullets):
                if not isinstance(bullet, str) or not bullet.strip():
                    continue
                anchor = semantic_anchor(bullet)
                family = f"employment.statement.{employer}.{anchor}"
                if re.search(r"scrum teams?", bullet, re.IGNORECASE):
                    family = f"team_scope.{employer}"
                claims.append(
                    _claim(
                        opened=opened,
                        canonical_key=f"employment.{employer}.{anchor}",
                        category="achievement",
                        subject=company,
                        value=bullet,
                        display_value=bullet,
                        locator=f"$.experience[{index}].bullets[{bullet_index}]",
                        employer_key=employer,
                        period=period,
                        semantic_family=family,
                    )
                )

        for field, category in (
            ("education", "education"),
            ("certifications", "certification"),
            ("languages", "language"),
        ):
            values = payload.get(field, [])
            if not isinstance(values, list):
                raise MalformedSourceError(f"The {field} section must be a list.")
            for index, value in enumerate(values):
                if isinstance(value, str):
                    claims.append(
                        _claim(
                            opened=opened,
                            canonical_key=f"{category}.{semantic_anchor(value)}",
                            category=category,
                            subject="Varun Nanduri",
                            value=value,
                            display_value=value,
                            locator=f"$.{field}[{index}]",
                        )
                    )

        competencies = payload.get("competencies", {})
        if isinstance(competencies, dict):
            for name, value in competencies.items():
                if isinstance(value, str):
                    claims.append(
                        _claim(
                            opened=opened,
                            canonical_key=f"skills.{slugify(str(name))}",
                            category="skill",
                            subject="Varun Nanduri",
                            value=value,
                            display_value=value,
                            locator=f"$.competencies.{name}",
                        )
                    )
        return ImportResult(spec.key, opened.content_hash, mark_ambiguous_collisions(claims))
