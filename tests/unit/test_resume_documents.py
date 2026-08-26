from importlib.util import find_spec

from job_search_cockpit.phase1_contract.snapshots import (
    Phase1ResumeFactProjection,
    Phase1ResumeFactSnapshot,
)
from job_search_cockpit.phase2.resume_documents import build_canonical_resume_document


def test_approved_resume_rendering_dependencies_are_runtime_available() -> None:
    assert find_spec("docx") is not None
    assert find_spec("reportlab") is not None
    assert find_spec("pypdf") is not None


def test_canonical_resume_document_is_deterministic_and_uses_approved_wording() -> None:
    projection = Phase1ResumeFactProjection(
        requirement_ids=("skills.python",),
        facts=(
            Phase1ResumeFactSnapshot(
                requirement_id="skills.python",
                claim_id="sanitized-claim-1",
                revision_id="sanitized-revision-1",
                support_assertion_id="sanitized-support-1",
                safe_wording="Built Python services.",
                employer_key=None,
                period_start=None,
                period_end=None,
            ),
        ),
        profile_fingerprint="a" * 64,
        profile_generation=1,
        readiness_fingerprint="b" * 64,
        readiness_generation=1,
        authority_fingerprint="c" * 64,
        authority_generation=1,
        restore_generation=0,
        fingerprint="d" * 64,
    )

    first = build_canonical_resume_document(projection)
    second = build_canonical_resume_document(projection)

    assert first == second
    assert first.entries[0].safe_wording == "Built Python services."
    assert first.plain_text == "Varun Resume\n\nSelected Experience\n\nBuilt Python services."
    assert len(first.content_fingerprint) == 64
