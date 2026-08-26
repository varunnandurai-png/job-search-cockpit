from pathlib import Path

from PIL import Image

from job_search_cockpit.phase1_contract.snapshots import (
    Phase1ResumeFactProjection,
    Phase1ResumeFactSnapshot,
)
from job_search_cockpit.phase2.document_rendering import (
    LocalResumeRenderer,
    extract_docx_text,
    extract_pdf_text,
)
from job_search_cockpit.phase2.resume_documents import build_canonical_resume_document


def test_renderer_creates_readable_equivalent_docx_and_pdf_from_one_model(tmp_path: Path) -> None:
    headshot_path = tmp_path / "placeholder.png"
    Image.new("RGB", (120, 120), color=(210, 220, 230)).save(headshot_path)
    document = build_canonical_resume_document(
        Phase1ResumeFactProjection(
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
    )

    rendered = LocalResumeRenderer().render(
        document=document,
        output_dir=tmp_path / "output",
        stem="Varun_Resume_Acme",
        headshot_path=headshot_path,
    )

    assert rendered.docx_path.exists()
    assert rendered.pdf_path.exists()
    assert extract_docx_text(rendered.docx_path) == document.plain_text
    assert extract_pdf_text(rendered.pdf_path) == document.plain_text
