from dataclasses import dataclass

from job_search_cockpit.phase1_contract.snapshots import (
    Phase1ResumeFactProjection,
    canonical_fingerprint,
)
from job_search_cockpit.phase2.requirements import (
    RequirementLedger,
    RequirementLedgerError,
    build_requirement_ledger,
)


class FinalisationError(ValueError):
    """Raised when a local résumé finalisation cannot proceed safely."""


@dataclass(frozen=True, slots=True)
class FinalisationPlan:
    job_id: str
    job_revision_id: str
    projection_fingerprint: str
    content_fingerprint: str
    requirements: RequirementLedger


def prepare_finalisation(
    *,
    job_id: str,
    job_revision_id: str,
    resume_kind: str,
    projection: Phase1ResumeFactProjection,
) -> FinalisationPlan:
    if resume_kind == "generic":
        raise FinalisationError("A generic résumé cannot be finalised.")
    if resume_kind != "tailored":
        raise FinalisationError("Choose a tailored résumé or stop.")
    if not job_id.strip() or not job_revision_id.strip():
        raise FinalisationError("A verified job revision is required.")
    try:
        requirements = build_requirement_ledger(projection)
    except RequirementLedgerError as error:
        raise FinalisationError("The approved fact projection is incomplete.") from error
    if not requirements.drafting_allowed:
        raise FinalisationError(
            "Every job requirement needs approved evidence before finalisation."
        )
    return FinalisationPlan(
        job_id=job_id,
        job_revision_id=job_revision_id,
        projection_fingerprint=projection.fingerprint,
        content_fingerprint=canonical_fingerprint(
            {
                "job_id": job_id,
                "job_revision_id": job_revision_id,
                "projection_fingerprint": projection.fingerprint,
            }
        ),
        requirements=requirements,
    )
