import pytest

from job_search_cockpit.phase1_contract.snapshots import (
    Phase1ResumeFactProjection,
    Phase1ResumeFactSnapshot,
)
from job_search_cockpit.phase2.finalisation import FinalisationError, prepare_finalisation


def _projection(*facts: Phase1ResumeFactSnapshot) -> Phase1ResumeFactProjection:
    return Phase1ResumeFactProjection(
        requirement_ids=("skills.python",),
        facts=facts,
        profile_fingerprint="a" * 64,
        profile_generation=1,
        readiness_fingerprint="b" * 64,
        readiness_generation=1,
        authority_fingerprint="c" * 64,
        authority_generation=1,
        restore_generation=0,
        fingerprint="d" * 64,
    )


def test_finalisation_rejects_a_generic_resume_before_creating_a_plan() -> None:
    with pytest.raises(FinalisationError, match="generic résumé"):
        prepare_finalisation(
            job_id="sanitized-job-1",
            job_revision_id="sanitized-revision-1",
            resume_kind="generic",
            projection=_projection(),
        )


def test_finalisation_rejects_a_projection_with_requirement_gaps() -> None:
    with pytest.raises(FinalisationError, match="approved evidence"):
        prepare_finalisation(
            job_id="sanitized-job-1",
            job_revision_id="sanitized-revision-1",
            resume_kind="tailored",
            projection=_projection(),
        )


def test_finalisation_plan_is_bound_to_the_approved_projection() -> None:
    projection = _projection(
        Phase1ResumeFactSnapshot(
            requirement_id="skills.python",
            claim_id="sanitized-claim-1",
            revision_id="sanitized-revision-1",
            support_assertion_id="sanitized-support-1",
            safe_wording="Built Python services.",
            employer_key=None,
            period_start=None,
            period_end=None,
        )
    )

    plan = prepare_finalisation(
        job_id="sanitized-job-1",
        job_revision_id="sanitized-revision-1",
        resume_kind="tailored",
        projection=projection,
    )

    assert plan.projection_fingerprint == projection.fingerprint
    assert len(plan.content_fingerprint) == 64
