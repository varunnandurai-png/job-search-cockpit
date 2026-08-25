from contextlib import suppress

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response

from job_search_cockpit.phase2.activation import Phase2ActivationService
from job_search_cockpit.phase2.types import ActivationCommand, Phase2ActivationUnavailable

router = APIRouter()


def _activation_service(request: Request) -> Phase2ActivationService | None:
    service = request.app.state.prepared.services.phase2_activation_service
    return service if isinstance(service, Phase2ActivationService) else None


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
    response: Response = request.app.state.templates.TemplateResponse(
        request,
        "phase2_local_review.html",
        {"csrf_token": request.app.state.launch_session.csrf_token},
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
