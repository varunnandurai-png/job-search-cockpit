from dataclasses import dataclass

from job_search_cockpit.phase1_contract.snapshots import (
    Phase1ResumeFactProjection,
    canonical_fingerprint,
)
from job_search_cockpit.phase2.requirements import (
    RequirementLedgerError,
    build_requirement_ledger,
)


class ResumeDocumentError(ValueError):
    """Raised when approved facts cannot form a local resume document."""


@dataclass(frozen=True, slots=True)
class CanonicalResumeEntry:
    requirement_id: str
    safe_wording: str
    claim_id: str
    revision_id: str
    support_assertion_id: str
    employer_key: str | None
    period_start: str | None
    period_end: str | None


@dataclass(frozen=True, slots=True)
class CanonicalResumeDocument:
    title: str
    section_title: str
    entries: tuple[CanonicalResumeEntry, ...]
    plain_text: str
    content_fingerprint: str


def build_canonical_resume_document(
    projection: Phase1ResumeFactProjection,
) -> CanonicalResumeDocument:
    try:
        ledger = build_requirement_ledger(projection)
    except RequirementLedgerError as error:
        raise ResumeDocumentError("The approved fact projection is incomplete.") from error
    if not ledger.drafting_allowed:
        raise ResumeDocumentError("Every job requirement needs approved evidence.")

    entries = tuple(
        CanonicalResumeEntry(
            requirement_id=requirement.requirement_id,
            safe_wording=requirement.safe_wording,
            claim_id=requirement.claim_id,
            revision_id=requirement.revision_id,
            support_assertion_id=requirement.support_assertion_id,
            employer_key=requirement.employer_key,
            period_start=requirement.period_start,
            period_end=requirement.period_end,
        )
        for requirement in ledger.supported
    )
    title = "Varun Resume"
    section_title = "Selected Experience"
    plain_text = "\n\n".join((title, section_title, *(entry.safe_wording for entry in entries)))
    return CanonicalResumeDocument(
        title=title,
        section_title=section_title,
        entries=entries,
        plain_text=plain_text,
        content_fingerprint=canonical_fingerprint(
            {
                "title": title,
                "section_title": section_title,
                "entries": [
                    {
                        "requirement_id": entry.requirement_id,
                        "safe_wording": entry.safe_wording,
                        "claim_id": entry.claim_id,
                        "revision_id": entry.revision_id,
                        "support_assertion_id": entry.support_assertion_id,
                        "employer_key": entry.employer_key,
                        "period_start": entry.period_start,
                        "period_end": entry.period_end,
                    }
                    for entry in entries
                ],
            }
        ),
    )
