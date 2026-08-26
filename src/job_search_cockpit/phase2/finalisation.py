# ruff: noqa: E501
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from re import sub
from tempfile import TemporaryDirectory
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from job_search_cockpit.phase1_contract.snapshots import (
    Phase1ResumeFactProjection,
    Phase1ResumeFactProjectionRequest,
    canonical_fingerprint,
)
from job_search_cockpit.phase2.document_rendering import (
    LocalResumeRenderer,
    extract_docx_text,
    extract_pdf_text,
)
from job_search_cockpit.phase2.models import (
    Phase2FinalResumeArtifact,
    Phase2ResumeDocumentAttempt,
    Phase2ResumeDocumentAttemptEvent,
    Phase2ResumeRequirementLedger,
)
from job_search_cockpit.phase2.mutation import Phase2MutationCoordinator
from job_search_cockpit.phase2.requirements import (
    RequirementLedger,
    RequirementLedgerError,
    build_requirement_ledger,
)
from job_search_cockpit.phase2.resume_documents import build_canonical_resume_document
from job_search_cockpit.phase2.resume_safety import (
    VerifiedJobPreparationPort,
    assert_phase3_requirement_ledger,
)
from job_search_cockpit.ports import Phase1MatchingPort


class FinalisationError(ValueError):
    """Raised when a local résumé finalisation cannot proceed safely."""


@dataclass(frozen=True, slots=True)
class FinalisationPlan:
    job_id: str
    job_revision_id: str
    projection_fingerprint: str
    content_fingerprint: str
    requirements: RequirementLedger


FINALISE_CONFIRMATION = "FINALISE RESUME FOR THIS VERIFIED JOB"


@dataclass(frozen=True, slots=True)
class ResumeDocumentReview:
    attempt_id: str
    job_id: str
    plain_text: str
    content_fingerprint: str


@dataclass(frozen=True, slots=True)
class FinaliseResumeCommand:
    attempt_id: str
    confirmation: str
    headshot_path: Path


@dataclass(frozen=True, slots=True)
class FinalResumeArtifact:
    attempt_id: str
    docx_path: Path
    pdf_path: Path
    content_fingerprint: str


class LocalResumeFinalisationService:
    """Creates the two local files only after every binding is still current."""

    def __init__(
        self, preparation_port: VerifiedJobPreparationPort, phase1_port: Phase1MatchingPort,
        coordinator: Phase2MutationCoordinator, output_dir: Path,
        renderer: LocalResumeRenderer | None = None,
    ) -> None:
        self._preparation_port = preparation_port
        self._phase1_port = phase1_port
        self._coordinator = coordinator
        self._output_dir = output_dir
        self._renderer = renderer or LocalResumeRenderer()

    def start_review(self, job_id: str) -> ResumeDocumentReview:
        authorization = self._preparation_port.authorization_for_resume(job_id)
        requirement_ids = assert_phase3_requirement_ledger(authorization)
        authorization = self._preparation_port.revalidate_resume_authorization(authorization)
        projection = self._phase1_port.resume_fact_projection(
            Phase1ResumeFactProjectionRequest(requirement_ids=requirement_ids)
        )
        if self._phase1_port.revalidate_resume_fact_projection(projection) != projection:
            raise FinalisationError("Approved résumé facts changed before review.")
        document = build_canonical_resume_document(projection)
        attempt_id = self._record_attempt(authorization, projection.fingerprint, document.content_fingerprint)
        return ResumeDocumentReview(attempt_id, job_id, document.plain_text, document.content_fingerprint)

    def finalise(self, command: FinaliseResumeCommand) -> FinalResumeArtifact:
        if command.confirmation != FINALISE_CONFIRMATION:
            raise FinalisationError("Type the exact finalisation confirmation.")
        if not command.headshot_path.is_file():
            raise FinalisationError("A local professional headshot is required.")
        attempt = self._attempt(command.attempt_id)
        authorization = self._preparation_port.authorization_for_resume(attempt.job_id)
        if authorization.authorization_id != attempt.authorization_id:
            raise FinalisationError("The verified job authorization changed.")
        requirement_ids = assert_phase3_requirement_ledger(authorization)
        authorization = self._preparation_port.revalidate_resume_authorization(authorization)
        projection = self._phase1_port.resume_fact_projection(Phase1ResumeFactProjectionRequest(requirement_ids=requirement_ids))
        if self._phase1_port.revalidate_resume_fact_projection(projection) != projection:
            raise FinalisationError("Approved résumé facts changed before finalisation.")
        document = build_canonical_resume_document(projection)
        if (projection.fingerprint, document.content_fingerprint) != (attempt.projection_fingerprint, attempt.canonical_model_fingerprint):
            raise FinalisationError("The reviewed résumé content changed.")
        self._output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        stem = self._filename_stem(authorization.company_name, authorization.role_name)
        with TemporaryDirectory(dir=self._output_dir) as temp_dir:
            rendered = self._renderer.render(document=document, output_dir=Path(temp_dir) / "files", stem=stem, headshot_path=command.headshot_path)
            if extract_docx_text(rendered.docx_path) != document.plain_text or extract_pdf_text(rendered.pdf_path) != document.plain_text:
                self._record_failure(attempt.id, "content_mismatch")
                raise FinalisationError("The rendered files do not match the reviewed résumé.")
            artifact = self._record_artifact(attempt, rendered.docx_path, rendered.pdf_path, document.content_fingerprint)
            artifact.docx_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            rendered.docx_path.replace(artifact.docx_path)
            rendered.pdf_path.replace(artifact.pdf_path)
        return artifact

    def _record_attempt(self, authorization: object, projection_fingerprint: str, content_fingerprint: str) -> str:
        from job_search_cockpit.phase2.resume_safety import VerifiedJobPreparationAuthorization
        assert isinstance(authorization, VerifiedJobPreparationAuthorization)
        def insert(session: Session) -> str:
            ledger = session.scalar(select(Phase2ResumeRequirementLedger).where(Phase2ResumeRequirementLedger.job_id == authorization.job_id, Phase2ResumeRequirementLedger.job_revision_id == authorization.job_revision_id, Phase2ResumeRequirementLedger.requirement_ledger_fingerprint == authorization.requirement_ledger_fingerprint))
            if ledger is None:
                raise FinalisationError("The verified job requirement ledger is unavailable.")
            attempt = Phase2ResumeDocumentAttempt(id=str(uuid4()), job_id=authorization.job_id, job_revision_id=authorization.job_revision_id, requirement_ledger_id=ledger.id, requirement_ledger_fingerprint=authorization.requirement_ledger_fingerprint, requirement_ids_json=list(authorization.requirement_ids), authorization_id=authorization.authorization_id, authorization_nonce=authorization.authorization_nonce, authorization_expires_at=authorization.expires_at, projection_fingerprint=projection_fingerprint, canonical_model_fingerprint=content_fingerprint, phase1_profile_fingerprint=authorization.phase1_profile_fingerprint, phase1_profile_generation=authorization.phase1_profile_generation, phase1_readiness_fingerprint=authorization.phase1_readiness_fingerprint, phase1_readiness_generation=authorization.phase1_readiness_generation, phase1_authority_fingerprint=authorization.phase1_authority_fingerprint, phase1_authority_generation=authorization.phase1_authority_generation, phase1_restore_generation=authorization.phase1_restore_generation, phase2_activation_generation=authorization.phase2_activation_generation, phase2_restore_generation=authorization.phase2_restore_generation)
            session.add(attempt)
            session.flush()
            return attempt.id
        try:
            return self._coordinator.run(insert, "record_resume_document_review")
        except IntegrityError as error:
            raise FinalisationError("This verified job authorization has already been reviewed.") from error

    def _attempt(self, attempt_id: str) -> Phase2ResumeDocumentAttempt:
        with self._coordinator._session_factory() as session:
            attempt = session.get(Phase2ResumeDocumentAttempt, attempt_id)
            if attempt is None:
                raise FinalisationError("The résumé review is unavailable.")
            session.expunge(attempt)
            return attempt

    def _record_failure(self, attempt_id: str, reason: str) -> None:
        def insert(session: Session) -> None:
            session.add(
                Phase2ResumeDocumentAttemptEvent(
                    id=str(uuid4()), attempt_id=attempt_id, reason_code=reason
                )
            )

        self._coordinator.run(insert, "record_resume_finalisation_failure")

    def _record_artifact(self, attempt: Phase2ResumeDocumentAttempt, docx: Path, pdf: Path, content_fingerprint: str) -> FinalResumeArtifact:
        docx_target = self._output_dir / docx.name
        pdf_target = self._output_dir / pdf.name
        def insert(session: Session) -> FinalResumeArtifact:
            if session.scalar(select(Phase2FinalResumeArtifact).where(Phase2FinalResumeArtifact.attempt_id == attempt.id)) is not None:
                raise FinalisationError("This résumé review has already been finalised.")
            session.add(Phase2FinalResumeArtifact(id=str(uuid4()), attempt_id=attempt.id, job_id=attempt.job_id, job_revision_id=attempt.job_revision_id, projection_fingerprint=attempt.projection_fingerprint, content_fingerprint=content_fingerprint, docx_relative_path=docx_target.name, docx_sha256=_sha256(docx), docx_byte_length=docx.stat().st_size, pdf_relative_path=pdf_target.name, pdf_sha256=_sha256(pdf), pdf_byte_length=pdf.stat().st_size))
            session.flush()
            return FinalResumeArtifact(attempt.id, docx_target, pdf_target, content_fingerprint)
        return self._coordinator.run(insert, "record_final_resume_artifact")

    @staticmethod
    def _filename_stem(company: str, role: str) -> str:
        company_part = _safe_name(company)
        role_part = _safe_name(role)
        if not company_part or not role_part:
            raise FinalisationError("The verified company and role are unavailable.")
        return f"{role_part}_Varun_Resume_{company_part}"


def _safe_name(value: str) -> str:
    return sub(r"[^A-Za-z0-9]+", "_", value.strip()).strip("_")


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


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
