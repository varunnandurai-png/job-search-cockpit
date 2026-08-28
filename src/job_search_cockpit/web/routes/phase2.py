from contextlib import suppress
from pathlib import Path
from typing import Literal, cast

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response

from job_search_cockpit.phase2.activation import Phase2ActivationService
from job_search_cockpit.phase2.finalisation import (
    FINALISE_CONFIRMATION,
    FinalisationError,
    FinaliseResumeCommand,
    FinalResumeArtifact,
    ResumeDocumentReview,
)
from job_search_cockpit.phase2.resume_safety import ResumePreparationError
from job_search_cockpit.phase2.runtime import Phase2Runtime
from job_search_cockpit.phase2.types import ActivationCommand, Phase2ActivationUnavailable
from job_search_cockpit.phase2.verification import VerifyCandidateCommand

router = APIRouter()


def _activation_service(request: Request) -> Phase2ActivationService | None:
    service = request.app.state.prepared.services.phase2_activation_service
    return service if isinstance(service, Phase2ActivationService) else None


def _runtime(request: Request) -> Phase2Runtime | None:
    runtime = request.app.state.prepared.phase2_runtime
    return runtime if isinstance(runtime, Phase2Runtime) else None


@router.get("/phase-2/drive-backups/oauth/callback", response_class=HTMLResponse)
def drive_oauth_callback(request: Request) -> Response:
    """The sole route that may receive Google's cross-site loopback redirect."""
    runtime = _runtime(request)
    state = _bounded(request.query_params.get("state"), 120)
    code = _bounded(request.query_params.get("code"), 4096)
    if runtime is None or runtime.drive_backup_service is None or not state or not code:
        return PlainTextResponse("Google authorization is unavailable.", status_code=400)
    try:
        runtime.drive_backup_service.complete_authorization(
            state=state,
            code=code,
            session_id=request.app.state.launch_session.session_id,
        )
    except ValueError:
        return PlainTextResponse("Google authorization is unavailable.", status_code=400)
    return PlainTextResponse("Google authorization completed safely.")


@router.post("/phase-2/drive-backups")
async def request_drive_backup(request: Request) -> Response:
    form = await request.form()
    if not request.app.state.launch_session.valid_csrf(form.get("csrf_token")):
        return PlainTextResponse("Invalid request token.", status_code=403)
    runtime = _runtime(request)
    artifact_id = _bounded(form.get("final_artifact_id"), 120)
    if runtime is None or runtime.drive_backup_service is None or not artifact_id:
        return PlainTextResponse("Drive backup is unavailable.", status_code=400)
    callback_uri = (
        f"http://127.0.0.1:{request.app.state.active_port}"
        "/phase-2/drive-backups/oauth/callback"
    )
    try:
        result = runtime.drive_backup_service.request_backup(
            final_artifact_id=artifact_id,
            session_id=request.app.state.launch_session.session_id,
            redirect_uri=callback_uri,
        )
    except ValueError:
        return PlainTextResponse("Drive backup is unavailable.", status_code=400)
    if result.authorization_url is not None:
        return RedirectResponse(result.authorization_url, status_code=303)
    return RedirectResponse("/phase-2/review", status_code=303)


@router.get("/phase-2", response_class=HTMLResponse)
def activation_page(request: Request) -> Response:
    service = _activation_service(request)
    if service is None:
        context = {"state": "inactive", "blocker": "Phase II activation is unavailable."}
    else:
        view = service.validate_current()
        context = {"state": view.state, "blocker": service.activation_blocker() or ""}
    response: Response = request.app.state.templates.TemplateResponse(
        request,
        "phase2_activation.html",
        {**context, "csrf_token": request.app.state.launch_session.csrf_token},
    )
    return response


@router.get("/phase-2/review", response_class=HTMLResponse)
def local_review_page(request: Request) -> Response:
    runtime = _runtime(request)
    status = runtime.discovery_service.status_view() if runtime is not None else None
    response: Response = request.app.state.templates.TemplateResponse(
        request,
        "phase2_local_review.html",
        {"csrf_token": request.app.state.launch_session.csrf_token, "discovery_status": status},
    )
    return response


@router.get("/phase-2/assessments", response_class=HTMLResponse)
def assessment_page(request: Request) -> Response:
    runtime = _runtime(request)
    review = runtime.assessment_review_service.current_view() if runtime is not None else None
    response: Response = request.app.state.templates.TemplateResponse(
        request,
        "phase2_assessments.html",
        {"assessment_review": review},
    )
    return response


@router.post("/phase-2/resume-reviews")
async def start_resume_review(request: Request) -> Response:
    form = await request.form()
    if not request.app.state.launch_session.valid_csrf(form.get("csrf_token")):
        return PlainTextResponse("Invalid request token.", status_code=403)
    runtime = _runtime(request)
    job_id = _bounded(form.get("job_id"), 120)
    if runtime is None or not job_id:
        return _resume_error(request)
    try:
        review = runtime.resume_finalisation_service.start_review(job_id)
    except (FinalisationError, ResumePreparationError, ValueError):
        return _resume_error(request)
    return RedirectResponse(
        f"/phase-2/resume-reviews/{review.attempt_id}", status_code=303
    )


@router.get("/phase-2/resume-reviews/{attempt_id}", response_class=HTMLResponse)
def resume_review(request: Request, attempt_id: str) -> Response:
    runtime = _runtime(request)
    attempt_id = _bounded(attempt_id, 120)
    if runtime is None or not attempt_id:
        return _resume_error(request)
    try:
        review = runtime.resume_finalisation_service.review_for(attempt_id)
    except (FinalisationError, ResumePreparationError, ValueError):
        return _resume_error(request)
    artifact: FinalResumeArtifact | None = None
    with suppress(FinalisationError, ResumePreparationError, ValueError):
        artifact = runtime.resume_finalisation_service.artifacts_for(attempt_id)
    return _resume_page(request, review, artifact)


@router.post("/phase-2/resume-reviews/{attempt_id}/finalise")
async def finalise_resume(request: Request, attempt_id: str) -> Response:
    form = await request.form()
    if not request.app.state.launch_session.valid_csrf(form.get("csrf_token")):
        return PlainTextResponse("Invalid request token.", status_code=403)
    runtime = _runtime(request)
    attempt_id = _bounded(attempt_id, 120)
    confirmation = str(form.get("confirmation", ""))
    headshot_value = _bounded(form.get("headshot_path"), 4096)
    headshot_path = Path(headshot_value)
    if (
        runtime is None
        or not attempt_id
        or confirmation != FINALISE_CONFIRMATION
        or not headshot_value
        or not headshot_path.is_absolute()
    ):
        return _resume_error(request)
    try:
        runtime.resume_finalisation_service.finalise(
            FinaliseResumeCommand(attempt_id, confirmation, headshot_path)
        )
    except (FinalisationError, ResumePreparationError, ValueError):
        return _resume_error(request)
    return RedirectResponse(f"/phase-2/resume-reviews/{attempt_id}", status_code=303)


def _resume_page(
    request: Request,
    review: ResumeDocumentReview | None,
    artifact: FinalResumeArtifact | None,
    *,
    error: str = "",
    status_code: int = 200,
) -> Response:
    response: Response = request.app.state.templates.TemplateResponse(
        request,
        "phase2_local_review.html",
        {
            "csrf_token": request.app.state.launch_session.csrf_token,
            "resume_review": review,
            "resume_artifact": artifact,
            "error": error,
            "discovery_status": None,
        },
        status_code=status_code,
    )
    return response


def _resume_error(request: Request) -> Response:
    return _resume_page(
        request,
        None,
        None,
        error="Resume finalisation is unavailable for this request.",
        status_code=400,
    )


def _bounded(value: object, maximum: int) -> str:
    candidate = str(value or "").strip()
    return candidate if len(candidate) <= maximum else ""


@router.post("/phase-2/activate")
async def activate(request: Request) -> Response:
    if not request.app.state.launch_session.valid_csrf((await request.form()).get("csrf_token")):
        return PlainTextResponse("Invalid request token.", status_code=403)
    service = _activation_service(request)
    if service is not None:
        form = await request.form()
        with suppress(Phase2ActivationUnavailable):
            service.activate(
                ActivationCommand(
                    actor="Varun",
                    confirmation=str(form.get("confirmation", "")),
                    reason=str(form.get("reason", "")),
                )
            )
    return RedirectResponse("/phase-2", status_code=303)


@router.post("/phase-2/verify")
async def verify_candidate(request: Request) -> Response:
    form = await request.form()
    if not request.app.state.launch_session.valid_csrf(form.get("csrf_token")):
        return PlainTextResponse("Invalid request token.", status_code=403)
    runtime = _runtime(request)
    if runtime is not None:
        codes = tuple(
            code.strip()
            for code in str(form.get("unknown_mandatory_rule_codes", "")).split(",")
            if code.strip()
        )
        with suppress(Phase2ActivationUnavailable, ResumePreparationError, ValueError):
            runtime.verified_job_authorization_service.verify(
                VerifyCandidateCommand(
                    job_revision_id=str(form.get("job_revision_id", "")),
                    selected_location_path=str(form.get("selected_location_path", "")),
                    actor=str(form.get("actor", "")),
                    reason=str(form.get("reason", "")),
                    confirmation=str(form.get("confirmation", "")),
                    eligibility=_eligibility(form.get("eligibility")),
                    unknown_mandatory_rule_codes=codes,
                )
            )
    return RedirectResponse("/phase-2/review", status_code=303)


def _eligibility(value: object) -> Literal["eligible", "ineligible", "needs_clarification"]:
    candidate = str(value)
    if candidate in {"eligible", "ineligible", "needs_clarification"}:
        return cast(Literal["eligible", "ineligible", "needs_clarification"], candidate)
    return "needs_clarification"
