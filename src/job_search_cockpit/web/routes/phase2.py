from contextlib import suppress
from typing import Literal, cast

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response

from job_search_cockpit.phase2.activation import Phase2ActivationService
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
