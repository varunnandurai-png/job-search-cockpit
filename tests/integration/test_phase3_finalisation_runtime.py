from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select

from job_search_cockpit.phase2 import finalisation as finalisation_module
from job_search_cockpit.phase2.document_rendering import (
    LocalResumeRenderer,
    RenderedResumeFiles,
)
from job_search_cockpit.phase2.finalisation import (
    FINALISE_CONFIRMATION,
    FinalisationError,
    FinaliseResumeCommand,
)
from job_search_cockpit.phase2.models import (
    Phase2FinalResumeArtifact,
    Phase2ResumeDocumentAttempt,
    Phase2ResumeDocumentAttemptEvent,
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


def test_review_lookup_revalidates_the_bound_authorization_and_projection(
    tmp_path: Path,
) -> None:
    runtime = build_synthetic_phase3_runtime(tmp_path)
    try:
        started = runtime.service.start_review("job-1")

        reviewed = runtime.service.review_for(started.attempt_id)

        assert reviewed == started
        assert reviewed.job_revision_id == "job-revision-1"
        assert reviewed.requirements.drafting_allowed is True
        assert reviewed.exact_confirmation == FINALISE_CONFIRMATION
    finally:
        runtime.close()


def test_review_lookup_denies_canonical_content_drift_with_reused_projection_fingerprint(
    tmp_path: Path,
) -> None:
    runtime = build_synthetic_phase3_runtime(tmp_path)
    try:
        started = runtime.service.start_review("job-1")
        projection = runtime.phase1_port.projection
        changed_fact = projection.facts[0].model_copy(
            update={"safe_wording": "Changed synthetic wording."}
        )
        runtime.phase1_port.projection = projection.model_copy(
            update={"facts": (changed_fact,)}
        )

        with pytest.raises(FinalisationError, match="reviewed résumé content changed"):
            runtime.service.review_for(started.attempt_id)
    finally:
        runtime.close()


def test_review_lookup_rechecks_current_job_eligibility(tmp_path: Path) -> None:
    runtime = build_synthetic_phase3_runtime(tmp_path)
    try:
        started = runtime.service.start_review("job-1")
        current = runtime.preparation_port.authorizations["job-1"]
        runtime.preparation_port.authorizations["job-1"] = replace(
            current, eligibility="ineligible"
        )

        with pytest.raises(FinalisationError, match="not eligible"):
            runtime.service.review_for(started.attempt_id)
    finally:
        runtime.close()


def test_review_lookup_rechecks_current_authorization_expiry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = build_synthetic_phase3_runtime(tmp_path)
    try:
        started = runtime.service.start_review("job-1")

        class AfterExpiry(datetime):
            @classmethod
            def now(cls, tz=None):  # type: ignore[no-untyped-def]
                return cls(2100, 1, 1, tzinfo=UTC)

        monkeypatch.setattr(finalisation_module, "datetime", AfterExpiry)

        with pytest.raises(FinalisationError, match="authorization has expired"):
            runtime.service.review_for(started.attempt_id)
    finally:
        runtime.close()


def test_review_start_rejects_a_job_mismatched_authorization_without_metadata(
    tmp_path: Path,
) -> None:
    runtime = build_synthetic_phase3_runtime(tmp_path)
    try:
        current = runtime.preparation_port.authorizations["job-1"]
        runtime.preparation_port.authorizations["job-1"] = replace(
            current, job_id="job-2"
        )

        with pytest.raises(FinalisationError, match="authorization changed"):
            runtime.service.start_review("job-1")

        assert _attempt_count(runtime) == 0
        assert not (tmp_path / "data" / "final-resumes").exists()
    finally:
        runtime.close()


def test_review_start_rejects_expired_authorization_without_metadata(
    tmp_path: Path,
) -> None:
    runtime = build_synthetic_phase3_runtime(tmp_path)
    try:
        current = runtime.preparation_port.authorizations["job-1"]
        runtime.preparation_port.authorizations["job-1"] = replace(
            current, expires_at=datetime(2020, 1, 1, tzinfo=UTC)
        )

        with pytest.raises(FinalisationError, match="authorization has expired"):
            runtime.service.start_review("job-1")

        assert _attempt_count(runtime) == 0
        assert not (tmp_path / "data" / "final-resumes").exists()
    finally:
        runtime.close()


def test_review_start_rejects_incomplete_authorization_binding_without_metadata(
    tmp_path: Path,
) -> None:
    runtime = build_synthetic_phase3_runtime(tmp_path)
    try:
        current = runtime.preparation_port.authorizations["job-1"]
        runtime.preparation_port.authorizations["job-1"] = replace(
            current, authorization_nonce=""
        )

        with pytest.raises(FinalisationError, match="binding is incomplete"):
            runtime.service.start_review("job-1")

        assert _attempt_count(runtime) == 0
        assert not (tmp_path / "data" / "final-resumes").exists()
    finally:
        runtime.close()


def test_review_start_blocks_missing_approved_requirement_evidence(
    tmp_path: Path,
) -> None:
    runtime = build_synthetic_phase3_runtime(tmp_path)
    try:
        runtime.phase1_port.projection = runtime.phase1_port.projection.model_copy(
            update={"facts": ()}
        )

        with pytest.raises(ValueError, match="needs approved evidence"):
            runtime.service.start_review("job-1")

        assert _attempt_count(runtime) == 0
        assert not (tmp_path / "data" / "final-resumes").exists()
    finally:
        runtime.close()


def test_review_start_revalidates_authorization_immediately_before_record(
    tmp_path: Path,
) -> None:
    runtime = build_synthetic_phase3_runtime(tmp_path)
    try:
        original_port = runtime.preparation_port

        class DriftBeforeRecord:
            revalidation_count = 0

            def authorization_for_resume(self, job_id: str):  # type: ignore[no-untyped-def]
                return original_port.authorization_for_resume(job_id)

            def revalidate_resume_authorization(
                self, expected  # type: ignore[no-untyped-def]
            ):
                self.revalidation_count += 1
                if self.revalidation_count == 1:
                    return expected
                return replace(expected, phase2_activation_generation=2)

        runtime.service._preparation_port = DriftBeforeRecord()

        with pytest.raises(FinalisationError, match="authorization changed"):
            runtime.service.start_review("job-1")

        assert _attempt_count(runtime) == 0
        assert not (tmp_path / "data" / "final-resumes").exists()
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


def test_finalisation_never_overwrites_an_existing_output_pair(tmp_path: Path) -> None:
    runtime = build_synthetic_phase3_runtime(tmp_path)
    try:
        review = runtime.service.start_review("job-1")
        output_dir = tmp_path / "data" / "final-resumes"
        output_dir.mkdir(parents=True)
        existing_docx = output_dir / "Varun_Resume_Acme_Co.docx"
        existing_docx.write_bytes(b"keep-existing")

        with pytest.raises(FinalisationError, match="already exists"):
            runtime.service.finalise(
                FinaliseResumeCommand(
                    review.attempt_id, FINALISE_CONFIRMATION, runtime.headshot_path
                )
            )

        assert existing_docx.read_bytes() == b"keep-existing"
        assert not (output_dir / "Varun_Resume_Acme_Co.pdf").exists()
        assert _artifact_count(runtime) == 0
        assert _failure_reasons(runtime) == ["output_collision"]
        assert sorted(path.name for path in output_dir.iterdir()) == [existing_docx.name]
    finally:
        runtime.close()


def test_finalisation_revalidates_after_render_and_cleans_all_created_files(
    tmp_path: Path,
) -> None:
    runtime = build_synthetic_phase3_runtime(tmp_path)
    try:
        review = runtime.service.start_review("job-1")
        current = runtime.preparation_port.authorizations["job-1"]

        class DriftingRenderer(LocalResumeRenderer):
            def render(self, **kwargs):  # type: ignore[no-untyped-def]
                rendered = super().render(**kwargs)
                runtime.preparation_port.authorizations["job-1"] = replace(
                    current, phase2_activation_generation=2
                )
                return rendered

        runtime.service._renderer = DriftingRenderer()

        with pytest.raises(FinalisationError, match="authorization changed"):
            runtime.service.finalise(
                FinaliseResumeCommand(
                    review.attempt_id, FINALISE_CONFIRMATION, runtime.headshot_path
                )
            )

        output_dir = tmp_path / "data" / "final-resumes"
        assert not output_dir.exists() or list(output_dir.iterdir()) == []
        assert _artifact_count(runtime) == 0
    finally:
        runtime.close()


def test_replayed_finalisation_is_denied_without_changing_the_pair(tmp_path: Path) -> None:
    runtime = build_synthetic_phase3_runtime(tmp_path)
    try:
        review = runtime.service.start_review("job-1")
        command = FinaliseResumeCommand(
            review.attempt_id, FINALISE_CONFIRMATION, runtime.headshot_path
        )
        first = runtime.service.finalise(command)
        before = (first.docx_path.read_bytes(), first.pdf_path.read_bytes())

        with pytest.raises(FinalisationError, match="already been finalised"):
            runtime.service.finalise(command)

        assert (first.docx_path.read_bytes(), first.pdf_path.read_bytes()) == before
        assert _artifact_count(runtime) == 1
        assert _failure_reasons(runtime) == ["replay_denied"]
        assert sorted(path.name for path in first.docx_path.parent.iterdir()) == [
            first.docx_path.name,
            first.pdf_path.name,
        ]
    finally:
        runtime.close()


def test_renderer_failure_leaves_no_output_or_temporary_files(tmp_path: Path) -> None:
    runtime = build_synthetic_phase3_runtime(tmp_path)
    try:
        review = runtime.service.start_review("job-1")

        class FailingRenderer(LocalResumeRenderer):
            def render(self, **kwargs) -> RenderedResumeFiles:  # type: ignore[no-untyped-def]
                output_dir = kwargs["output_dir"]
                output_dir.mkdir(parents=True)
                (output_dir / "partial.docx").write_bytes(b"partial")
                raise RuntimeError("synthetic renderer failure")

        runtime.service._renderer = FailingRenderer()

        with pytest.raises(FinalisationError, match="failed safely"):
            runtime.service.finalise(
                FinaliseResumeCommand(
                    review.attempt_id, FINALISE_CONFIRMATION, runtime.headshot_path
                )
            )

        output_dir = tmp_path / "data" / "final-resumes"
        assert not output_dir.exists() or list(output_dir.iterdir()) == []
        assert _artifact_count(runtime) == 0
        assert _failure_reasons(runtime) == ["render_or_publication_failed"]
    finally:
        runtime.close()


def test_metadata_failure_removes_the_exclusively_published_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = build_synthetic_phase3_runtime(tmp_path)
    try:
        review = runtime.service.start_review("job-1")

        def fail_metadata(*_args: object, **_kwargs: object) -> object:
            raise FinalisationError("Synthetic metadata failure.")

        monkeypatch.setattr(runtime.service, "_record_artifact", fail_metadata)

        with pytest.raises(FinalisationError, match="metadata failure"):
            runtime.service.finalise(
                FinaliseResumeCommand(
                    review.attempt_id, FINALISE_CONFIRMATION, runtime.headshot_path
                )
            )

        output_dir = tmp_path / "data" / "final-resumes"
        assert list(output_dir.iterdir()) == []
        assert _artifact_count(runtime) == 0
    finally:
        runtime.close()


def test_artifact_access_denies_projection_drift_and_file_tampering(tmp_path: Path) -> None:
    runtime = build_synthetic_phase3_runtime(tmp_path)
    try:
        review = runtime.service.start_review("job-1")
        artifact = runtime.service.finalise(
            FinaliseResumeCommand(
                review.attempt_id, FINALISE_CONFIRMATION, runtime.headshot_path
            )
        )
        original_projection = runtime.phase1_port.projection
        runtime.phase1_port.projection = original_projection.model_copy(
            update={"fingerprint": "9" * 64}
        )

        with pytest.raises(FinalisationError, match="facts changed"):
            runtime.service.artifacts_for(review.attempt_id)

        runtime.phase1_port.projection = original_projection
        artifact.pdf_path.write_bytes(b"tampered")
        with pytest.raises(FinalisationError, match="failed verification"):
            runtime.service.artifacts_for(review.attempt_id)
    finally:
        runtime.close()


def _artifact_count(runtime: object) -> int:
    coordinator = runtime.coordinator  # type: ignore[attr-defined]
    with coordinator._session_factory() as session:
        return int(session.scalar(select(func.count(Phase2FinalResumeArtifact.id))) or 0)


def _attempt_count(runtime: object) -> int:
    coordinator = runtime.coordinator  # type: ignore[attr-defined]
    with coordinator._session_factory() as session:
        return int(session.scalar(select(func.count(Phase2ResumeDocumentAttempt.id))) or 0)


def _failure_reasons(runtime: object) -> list[str]:
    coordinator = runtime.coordinator  # type: ignore[attr-defined]
    with coordinator._session_factory() as session:
        return list(
            session.scalars(
                select(Phase2ResumeDocumentAttemptEvent.reason_code).order_by(
                    Phase2ResumeDocumentAttemptEvent.created_at
                )
            )
        )
