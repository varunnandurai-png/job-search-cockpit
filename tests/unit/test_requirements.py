import pytest

from job_search_cockpit.phase1_contract.snapshots import (
    Phase1ResumeFactProjection,
    Phase1ResumeFactSnapshot,
)
from job_search_cockpit.phase2.requirements import RequirementLedgerError, build_requirement_ledger


def _projection(*facts: Phase1ResumeFactSnapshot) -> Phase1ResumeFactProjection:
    return Phase1ResumeFactProjection(
        requirement_ids=("skills.python", "skills.sql"),
        facts=facts,
        profile_fingerprint="a" * 64,
        profile_generation=1,
        readiness_fingerprint="b" * 64,
        readiness_generation=2,
        authority_fingerprint="c" * 64,
        authority_generation=3,
        restore_generation=4,
        fingerprint="d" * 64,
    )


def test_requirement_ledger_separates_supported_evidence_from_unknown_gaps() -> None:
    ledger = build_requirement_ledger(
        _projection(
            Phase1ResumeFactSnapshot(
                requirement_id="skills.python",
                claim_id="sanitized-claim-1",
                revision_id="sanitized-revision-1",
                support_assertion_id="sanitized-support-1",
                safe_wording="Python",
                employer_key=None,
                period_start=None,
                period_end=None,
            )
        )
    )

    assert ledger.drafting_allowed is False
    assert ledger.supported[0].requirement_id == "skills.python"
    assert ledger.supported[0].safe_wording == "Python"
    assert ledger.unsupported[0].requirement_id == "skills.sql"
    assert ledger.unsupported[0].reason == "No approved evidence found."


def test_requirement_ledger_rejects_a_fact_for_an_unrequested_requirement() -> None:
    projection = _projection(
        Phase1ResumeFactSnapshot(
            requirement_id="skills.python",
            claim_id="sanitized-claim-1",
            revision_id="sanitized-revision-1",
            support_assertion_id="sanitized-support-1",
            safe_wording="Python",
            employer_key=None,
            period_start=None,
            period_end=None,
        )
    ).model_copy(
        update={
            "facts": (
                Phase1ResumeFactSnapshot(
                    requirement_id="skills.unrequested",
                    claim_id="sanitized-claim-1",
                    revision_id="sanitized-revision-1",
                    support_assertion_id="sanitized-support-1",
                    safe_wording="Python",
                    employer_key=None,
                    period_start=None,
                    period_end=None,
                ),
            )
        }
    )

    with pytest.raises(RequirementLedgerError, match="unrequested requirement"):
        build_requirement_ledger(projection)
