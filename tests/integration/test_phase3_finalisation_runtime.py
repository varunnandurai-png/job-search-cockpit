from dataclasses import replace
from pathlib import Path

import pytest

from job_search_cockpit.phase2.finalisation import (
    FINALISE_CONFIRMATION,
    FinaliseResumeCommand,
)
from tests.support.phase3 import build_synthetic_phase3_runtime


def test_artifact_access_revalidates_and_returns_the_published_pair(tmp_path: Path) -> None:
    runtime = build_synthetic_phase3_runtime(tmp_path)
    try:
        review = runtime.service.start_review("job-1")
        finalised = runtime.service.finalise(
            FinaliseResumeCommand(
                review.attempt_id,
                FINALISE_CONFIRMATION,
                runtime.headshot_path,
            )
        )

        accessed = runtime.service.artifacts_for(review.attempt_id)

        assert accessed == finalised
        assert accessed.docx_path.name == "Varun_Resume_Acme_Co.docx"
        assert accessed.pdf_path.name == "Varun_Resume_Acme_Co.pdf"
        assert accessed.docx_path.is_file()
        assert accessed.pdf_path.is_file()
    finally:
        runtime.close()


def test_later_role_at_same_company_uses_role_prefix_without_overwrite(tmp_path: Path) -> None:
    runtime = build_synthetic_phase3_runtime(tmp_path)
    try:
        first = runtime.service.start_review("job-1")
        first_artifacts = runtime.service.finalise(
            FinaliseResumeCommand(first.attempt_id, FINALISE_CONFIRMATION, runtime.headshot_path)
        )
        first_docx_bytes = first_artifacts.docx_path.read_bytes()
        second = runtime.service.start_review("job-2")
        second_artifacts = runtime.service.finalise(
            FinaliseResumeCommand(second.attempt_id, FINALISE_CONFIRMATION, runtime.headshot_path)
        )

        assert first_artifacts.docx_path.name == "Varun_Resume_Acme_Co.docx"
        assert second_artifacts.docx_path.name == (
            "Lead_Product_Manager_Varun_Resume_Acme_Co.docx"
        )
        assert first_artifacts.docx_path.read_bytes() == first_docx_bytes
        assert first_artifacts.docx_path != second_artifacts.docx_path
    finally:
        runtime.close()


def test_artifact_access_denies_authorization_drift(tmp_path: Path) -> None:
    runtime = build_synthetic_phase3_runtime(tmp_path)
    try:
        review = runtime.service.start_review("job-1")
        runtime.service.finalise(
            FinaliseResumeCommand(review.attempt_id, FINALISE_CONFIRMATION, runtime.headshot_path)
        )
        current = runtime.preparation_port.authorizations["job-1"]
        runtime.preparation_port.authorizations["job-1"] = replace(
            current, phase2_activation_generation=2
        )

        with pytest.raises(ValueError, match="authorization changed"):
            runtime.service.artifacts_for(review.attempt_id)
    finally:
        runtime.close()
