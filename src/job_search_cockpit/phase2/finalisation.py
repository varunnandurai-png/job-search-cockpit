# ruff: noqa: E501
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from re import sub
from shutil import copyfileobj
from tempfile import TemporaryDirectory
from unicodedata import normalize
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
    Phase2JobRevision,
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
from job_search_cockpit.phase2.resume_documents import (
    CanonicalResumeDocument,
    build_canonical_resume_document,
)
from job_search_cockpit.phase2.resume_safety import (
    VerifiedJobPreparationAuthorization,
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
    job_revision_id: str
    plain_text: str
    content_fingerprint: str
    requirements: RequirementLedger
    exact_confirmation: str


@dataclass(frozen=True, slots=True)
class FinaliseResumeCommand:
    attempt_id: str
    confirmation: str
    headshot_path: Path


@dataclass(frozen=True, slots=True)
class FinalResumeArtifact:
    attempt_id: str
    job_id: str
    job_revision_id: str
    docx_path: Path
    docx_sha256: str
    docx_byte_length: int
    pdf_path: Path
    pdf_sha256: str
    pdf_byte_length: int
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
        if authorization.job_id != job_id:
            raise FinalisationError("The verified job authorization changed.")
        self._validate_authorization(authorization)
        requirement_ids = assert_phase3_requirement_ledger(authorization)
        revalidated = self._preparation_port.revalidate_resume_authorization(authorization)
        if revalidated != authorization:
            raise FinalisationError("The verified job authorization changed.")
        projection = self._phase1_port.resume_fact_projection(
            Phase1ResumeFactProjectionRequest(requirement_ids=requirement_ids)
        )
        if self._phase1_port.revalidate_resume_fact_projection(projection) != projection:
            raise FinalisationError("Approved résumé facts changed before review.")
        self._validate_projection_binding(authorization, projection)
        document = build_canonical_resume_document(projection)
        if self._preparation_port.revalidate_resume_authorization(authorization) != authorization:
            raise FinalisationError("The verified job authorization changed.")
        attempt_id = self._record_attempt(authorization, projection.fingerprint, document.content_fingerprint)
        return self.review_for(attempt_id)

    def review_for(self, attempt_id: str) -> ResumeDocumentReview:
        attempt = self._attempt(attempt_id)
        authorization = self._authorization_for_attempt(attempt)
        projection = self._projection_for_attempt(attempt, authorization)
        document = build_canonical_resume_document(projection)
        if document.content_fingerprint != attempt.canonical_model_fingerprint:
            raise FinalisationError("The reviewed résumé content changed.")
        requirements = build_requirement_ledger(projection)
        return ResumeDocumentReview(
            attempt_id=attempt.id,
            job_id=attempt.job_id,
            job_revision_id=attempt.job_revision_id,
            plain_text=document.plain_text,
            content_fingerprint=document.content_fingerprint,
            requirements=requirements,
            exact_confirmation=FINALISE_CONFIRMATION,
        )

    def finalise(self, command: FinaliseResumeCommand) -> FinalResumeArtifact:
        if command.confirmation != FINALISE_CONFIRMATION:
            raise FinalisationError("Type the exact finalisation confirmation.")
        if not command.headshot_path.is_file():
            raise FinalisationError("A local professional headshot is required.")
        attempt = self._attempt(command.attempt_id)
        published: tuple[Path, ...] = ()
        try:
            if self._artifact_row(attempt.id) is not None:
                raise FinalisationError("This résumé review has already been finalised.")
            authorization = self._authorization_for_attempt(attempt)
            document = self._document_for_attempt(attempt, authorization)
            self._output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            self._output_dir.chmod(0o700)
            stem = self._filename_stem(
                authorization.company_name,
                authorization.role_name,
                self._has_final_resume_for_company(authorization.company_name),
            )
            with TemporaryDirectory(dir=self._output_dir) as temp_dir:
                rendered = self._renderer.render(
                    document=document,
                    output_dir=Path(temp_dir) / "files",
                    stem=stem,
                    headshot_path=command.headshot_path,
                )
                if (
                    extract_docx_text(rendered.docx_path) != document.plain_text
                    or extract_pdf_text(rendered.pdf_path) != document.plain_text
                ):
                    raise FinalisationError(
                        "The rendered files do not match the reviewed résumé."
                    )
                self._document_for_attempt(
                    attempt, self._authorization_for_attempt(attempt)
                )
                docx_target = self._output_dir / rendered.docx_path.name
                pdf_target = self._output_dir / rendered.pdf_path.name
                published = self._publish_pair_exclusively(
                    rendered.docx_path, docx_target, rendered.pdf_path, pdf_target
                )
                self._document_for_attempt(
                    attempt, self._authorization_for_attempt(attempt)
                )
                return self._record_artifact(
                    attempt, docx_target, pdf_target, document.content_fingerprint
                )
        except Exception as error:
            for path in published:
                path.unlink(missing_ok=True)
            with suppress(Exception):
                self._record_failure(attempt.id, _failure_reason(error))
            if isinstance(error, FinalisationError):
                raise
            raise FinalisationError("Résumé finalisation failed safely.") from error

    def artifacts_for(self, attempt_id: str) -> FinalResumeArtifact:
        attempt = self._attempt(attempt_id)
        authorization = self._authorization_for_attempt(attempt)
        document = self._document_for_attempt(attempt, authorization)
        with self._coordinator._session_factory() as session:
            row = session.scalar(
                select(Phase2FinalResumeArtifact).where(
                    Phase2FinalResumeArtifact.attempt_id == attempt.id
                )
            )
            if row is None:
                raise FinalisationError("The final résumé artifacts are unavailable.")
            session.expunge(row)
        docx_path = self._artifact_path(row.docx_relative_path)
        pdf_path = self._artifact_path(row.pdf_relative_path)
        if (
            row.job_id != attempt.job_id
            or row.job_revision_id != attempt.job_revision_id
            or row.projection_fingerprint != attempt.projection_fingerprint
            or row.content_fingerprint != document.content_fingerprint
            or not docx_path.is_file()
            or not pdf_path.is_file()
            or docx_path.stat().st_size != row.docx_byte_length
            or pdf_path.stat().st_size != row.pdf_byte_length
            or _sha256(docx_path) != row.docx_sha256
            or _sha256(pdf_path) != row.pdf_sha256
            or extract_docx_text(docx_path) != document.plain_text
            or extract_pdf_text(pdf_path) != document.plain_text
        ):
            raise FinalisationError("The final résumé artifacts failed verification.")
        return self._artifact_view(row, docx_path, pdf_path)

    def _authorization_for_attempt(
        self, attempt: Phase2ResumeDocumentAttempt
    ) -> VerifiedJobPreparationAuthorization:
        authorization = self._preparation_port.authorization_for_resume(attempt.job_id)
        authorization = self._preparation_port.revalidate_resume_authorization(authorization)
        self._validate_authorization(authorization)
        stored_binding = (
            attempt.job_id,
            attempt.job_revision_id,
            attempt.authorization_id,
            attempt.authorization_nonce,
            _as_utc(attempt.authorization_expires_at),
            attempt.requirement_ledger_fingerprint,
            tuple(str(item) for item in attempt.requirement_ids_json),
            attempt.phase1_profile_fingerprint,
            attempt.phase1_profile_generation,
            attempt.phase1_readiness_fingerprint,
            attempt.phase1_readiness_generation,
            attempt.phase1_authority_fingerprint,
            attempt.phase1_authority_generation,
            attempt.phase1_restore_generation,
            attempt.phase2_activation_generation,
            attempt.phase2_restore_generation,
        )
        current_binding = (
            authorization.job_id,
            authorization.job_revision_id,
            authorization.authorization_id,
            authorization.authorization_nonce,
            _as_utc(authorization.expires_at),
            authorization.requirement_ledger_fingerprint,
            authorization.requirement_ids,
            authorization.phase1_profile_fingerprint,
            authorization.phase1_profile_generation,
            authorization.phase1_readiness_fingerprint,
            authorization.phase1_readiness_generation,
            authorization.phase1_authority_fingerprint,
            authorization.phase1_authority_generation,
            authorization.phase1_restore_generation,
            authorization.phase2_activation_generation,
            authorization.phase2_restore_generation,
        )
        if current_binding != stored_binding:
            raise FinalisationError("The verified job authorization changed.")
        return authorization

    def _projection_for_attempt(
        self,
        attempt: Phase2ResumeDocumentAttempt,
        authorization: VerifiedJobPreparationAuthorization,
    ) -> Phase1ResumeFactProjection:
        requirement_ids = assert_phase3_requirement_ledger(authorization)
        projection = self._phase1_port.resume_fact_projection(
            Phase1ResumeFactProjectionRequest(requirement_ids=requirement_ids)
        )
        if self._phase1_port.revalidate_resume_fact_projection(projection) != projection:
            raise FinalisationError("Approved résumé facts changed.")
        if (
            projection.fingerprint != attempt.projection_fingerprint
            or projection.profile_fingerprint != attempt.phase1_profile_fingerprint
            or projection.profile_generation != attempt.phase1_profile_generation
            or projection.readiness_fingerprint != attempt.phase1_readiness_fingerprint
            or projection.readiness_generation != attempt.phase1_readiness_generation
            or projection.authority_fingerprint != attempt.phase1_authority_fingerprint
            or projection.authority_generation != attempt.phase1_authority_generation
            or projection.restore_generation != attempt.phase1_restore_generation
        ):
            raise FinalisationError("Approved résumé facts changed.")
        self._validate_projection_binding(authorization, projection)
        return projection

    def _document_for_attempt(
        self,
        attempt: Phase2ResumeDocumentAttempt,
        authorization: VerifiedJobPreparationAuthorization,
    ) -> CanonicalResumeDocument:
        projection = self._projection_for_attempt(attempt, authorization)
        document = build_canonical_resume_document(projection)
        if document.content_fingerprint != attempt.canonical_model_fingerprint:
            raise FinalisationError("The reviewed résumé content changed.")
        return document

    @staticmethod
    def _validate_authorization(
        authorization: VerifiedJobPreparationAuthorization,
    ) -> None:
        required_values = (
            authorization.job_id,
            authorization.job_revision_id,
            authorization.selected_location_path_fingerprint,
            authorization.authorization_id,
            authorization.authorization_nonce,
            authorization.company_name,
            authorization.role_name,
        )
        fingerprints = (
            authorization.selected_location_path_fingerprint,
            authorization.phase1_profile_fingerprint,
            authorization.phase1_readiness_fingerprint,
            authorization.phase1_authority_fingerprint,
        )
        generations = (
            authorization.phase1_profile_generation,
            authorization.phase1_readiness_generation,
            authorization.phase1_authority_generation,
            authorization.phase1_restore_generation,
            authorization.phase2_activation_generation,
            authorization.phase2_restore_generation,
        )
        if (
            any(not value.strip() for value in required_values)
            or any(len(fingerprint) != 64 for fingerprint in fingerprints)
            or any(generation < 0 for generation in generations)
        ):
            raise FinalisationError("The verified job authorization binding is incomplete.")
        if _as_utc(authorization.expires_at) <= datetime.now(UTC):
            raise FinalisationError("The verified job authorization has expired.")
        if authorization.eligibility != "eligible" or authorization.unknown_mandatory_rule_codes:
            raise FinalisationError("The verified job is not eligible for finalisation.")

    @staticmethod
    def _validate_projection_binding(
        authorization: VerifiedJobPreparationAuthorization,
        projection: Phase1ResumeFactProjection,
    ) -> None:
        if (
            projection.requirement_ids != authorization.requirement_ids
            or projection.profile_fingerprint != authorization.phase1_profile_fingerprint
            or projection.profile_generation != authorization.phase1_profile_generation
            or projection.readiness_fingerprint != authorization.phase1_readiness_fingerprint
            or projection.readiness_generation != authorization.phase1_readiness_generation
            or projection.authority_fingerprint != authorization.phase1_authority_fingerprint
            or projection.authority_generation != authorization.phase1_authority_generation
            or projection.restore_generation != authorization.phase1_restore_generation
        ):
            raise FinalisationError("Approved résumé facts changed.")

    def _artifact_path(self, relative_path: str) -> Path:
        base = self._output_dir.resolve()
        candidate = (base / relative_path).resolve()
        try:
            candidate.relative_to(base)
        except ValueError as error:
            raise FinalisationError("The final résumé artifact path is invalid.") from error
        return candidate

    def _artifact_row(self, attempt_id: str) -> Phase2FinalResumeArtifact | None:
        with self._coordinator._session_factory() as session:
            row = session.scalar(
                select(Phase2FinalResumeArtifact).where(
                    Phase2FinalResumeArtifact.attempt_id == attempt_id
                )
            )
            if row is not None:
                session.expunge(row)
            return row

    def _has_final_resume_for_company(self, company: str) -> bool:
        company_key = _safe_name(company).casefold()
        with self._coordinator._session_factory() as session:
            employers = session.scalars(
                select(Phase2JobRevision.employer_name)
                .join(
                    Phase2ResumeDocumentAttempt,
                    Phase2ResumeDocumentAttempt.job_revision_id == Phase2JobRevision.id,
                )
                .join(
                    Phase2FinalResumeArtifact,
                    Phase2FinalResumeArtifact.attempt_id == Phase2ResumeDocumentAttempt.id,
                )
            ).all()
        return any(_safe_name(employer).casefold() == company_key for employer in employers)

    def _record_attempt(self, authorization: VerifiedJobPreparationAuthorization, projection_fingerprint: str, content_fingerprint: str) -> str:
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
        def insert(session: Session) -> FinalResumeArtifact:
            if session.scalar(select(Phase2FinalResumeArtifact).where(Phase2FinalResumeArtifact.attempt_id == attempt.id)) is not None:
                raise FinalisationError("This résumé review has already been finalised.")
            session.add(Phase2FinalResumeArtifact(id=str(uuid4()), attempt_id=attempt.id, job_id=attempt.job_id, job_revision_id=attempt.job_revision_id, projection_fingerprint=attempt.projection_fingerprint, content_fingerprint=content_fingerprint, docx_relative_path=docx.name, docx_sha256=_sha256(docx), docx_byte_length=docx.stat().st_size, pdf_relative_path=pdf.name, pdf_sha256=_sha256(pdf), pdf_byte_length=pdf.stat().st_size))
            session.flush()
            row = session.scalar(
                select(Phase2FinalResumeArtifact).where(
                    Phase2FinalResumeArtifact.attempt_id == attempt.id
                )
            )
            assert row is not None
            return self._artifact_view(row, docx, pdf)
        return self._coordinator.run(insert, "record_final_resume_artifact")

    @staticmethod
    def _publish_pair_exclusively(
        docx_source: Path,
        docx_target: Path,
        pdf_source: Path,
        pdf_target: Path,
    ) -> tuple[Path, Path]:
        published: list[Path] = []
        try:
            for source, target in (
                (docx_source, docx_target),
                (pdf_source, pdf_target),
            ):
                try:
                    with source.open("rb") as source_stream, target.open("xb") as target_stream:
                        copyfileobj(source_stream, target_stream)
                except FileExistsError as error:
                    raise FinalisationError(
                        "A résumé output with this filename already exists."
                    ) from error
                target.chmod(0o600)
                published.append(target)
        except Exception:
            for path in published:
                path.unlink(missing_ok=True)
            raise
        return docx_target, pdf_target

    @staticmethod
    def _artifact_view(
        row: Phase2FinalResumeArtifact, docx_path: Path, pdf_path: Path
    ) -> FinalResumeArtifact:
        return FinalResumeArtifact(
            attempt_id=row.attempt_id,
            job_id=row.job_id,
            job_revision_id=row.job_revision_id,
            docx_path=docx_path,
            docx_sha256=row.docx_sha256,
            docx_byte_length=row.docx_byte_length,
            pdf_path=pdf_path,
            pdf_sha256=row.pdf_sha256,
            pdf_byte_length=row.pdf_byte_length,
            content_fingerprint=row.content_fingerprint,
        )

    @staticmethod
    def _filename_stem(company: str, role: str, later_company_role: bool) -> str:
        company_part = _safe_name(company)
        role_part = _safe_name(role)
        if not company_part or not role_part:
            raise FinalisationError("The verified company and role are unavailable.")
        if later_company_role:
            return f"{role_part}_Varun_Resume_{company_part}"
        return f"Varun_Resume_{company_part}"


def _safe_name(value: str) -> str:
    ascii_value = normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return sub(r"[^A-Za-z0-9]+", "_", ascii_value.strip()).strip("_")[:80]


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _failure_reason(error: Exception) -> str:
    message = str(error).casefold()
    if "already been finalised" in message:
        return "replay_denied"
    if "already exists" in message:
        return "output_collision"
    if "authorization changed" in message:
        return "authorization_drift"
    if "facts changed" in message or "content changed" in message:
        return "projection_drift"
    if "rendered files" in message:
        return "content_mismatch"
    return "render_or_publication_failed"


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
