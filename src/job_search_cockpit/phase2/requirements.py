from dataclasses import dataclass

from job_search_cockpit.phase1_contract.snapshots import Phase1ResumeFactProjection


class RequirementLedgerError(ValueError):
    """Raised when a fact projection cannot safely explain requirement support."""


@dataclass(frozen=True, slots=True)
class SupportedRequirement:
    requirement_id: str
    claim_id: str
    revision_id: str
    support_assertion_id: str
    safe_wording: str
    employer_key: str | None
    period_start: str | None
    period_end: str | None


@dataclass(frozen=True, slots=True)
class UnsupportedRequirement:
    requirement_id: str
    reason: str = "No approved evidence found."


@dataclass(frozen=True, slots=True)
class RequirementLedger:
    projection_fingerprint: str
    supported: tuple[SupportedRequirement, ...]
    unsupported: tuple[UnsupportedRequirement, ...]

    @property
    def drafting_allowed(self) -> bool:
        return not self.unsupported


def build_requirement_ledger(projection: Phase1ResumeFactProjection) -> RequirementLedger:
    requested = set(projection.requirement_ids)
    by_requirement: dict[str, SupportedRequirement] = {}
    for fact in projection.facts:
        if fact.requirement_id not in requested:
            raise RequirementLedgerError("The fact projection contains an unrequested requirement.")
        if fact.requirement_id in by_requirement:
            raise RequirementLedgerError(
                "The fact projection contains duplicate requirement evidence."
            )
        if not all(
            (
                fact.claim_id.strip(),
                fact.revision_id.strip(),
                fact.support_assertion_id.strip(),
                fact.safe_wording.strip(),
            )
        ):
            raise RequirementLedgerError("The fact projection is incomplete.")
        by_requirement[fact.requirement_id] = SupportedRequirement(
            requirement_id=fact.requirement_id,
            claim_id=fact.claim_id,
            revision_id=fact.revision_id,
            support_assertion_id=fact.support_assertion_id,
            safe_wording=fact.safe_wording,
            employer_key=fact.employer_key,
            period_start=fact.period_start,
            period_end=fact.period_end,
        )
    supported = tuple(
        by_requirement[requirement_id]
        for requirement_id in projection.requirement_ids
        if requirement_id in by_requirement
    )
    unsupported = tuple(
        UnsupportedRequirement(requirement_id)
        for requirement_id in projection.requirement_ids
        if requirement_id not in by_requirement
    )
    return RequirementLedger(
        projection_fingerprint=projection.fingerprint,
        supported=supported,
        unsupported=unsupported,
    )
