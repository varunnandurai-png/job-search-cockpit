import re

from job_search_cockpit.config import SourceKind, SourceSpec
from job_search_cockpit.imports.grammar import evidence, normalize_text, semantic_anchor
from job_search_cockpit.imports.types import CandidateClaim, ImportResult, MalformedSourceError
from job_search_cockpit.sources import safe_open_source


class WorkflowImporter:
    def read(self, spec: SourceSpec) -> ImportResult:
        if spec.kind is not SourceKind.RESUME_WORKFLOW:
            raise MalformedSourceError("The source manifest declares the wrong format.")
        opened = safe_open_source(spec)
        try:
            lines = opened.content.decode("utf-8").splitlines()
        except UnicodeDecodeError as error:
            raise MalformedSourceError("The resume workflow is not valid UTF-8.") from error
        claims: list[CandidateClaim] = []
        for line_number, line in enumerate(lines, start=1):
            match = re.match(r"\s*\d+\.\s+(.+)", line)
            if not match:
                continue
            display = normalize_text(match.group(1))
            anchor = semantic_anchor(display)
            claims.append(
                CandidateClaim(
                    canonical_key=f"policy.resume.{anchor}",
                    category="policy",
                    subject="Resume generation",
                    value={"text": display},
                    display_value=display,
                    evidence=evidence(opened, f"line:{line_number}", display),
                    employer_key=None,
                    period_start=None,
                    period_end=None,
                    semantic_family=f"policy.resume.{anchor}",
                )
            )
        if not claims:
            raise MalformedSourceError("The resume workflow has no recognized numbered policies.")
        return ImportResult(spec.key, opened.content_hash, tuple(claims))
