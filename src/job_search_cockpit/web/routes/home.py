import time

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response

from job_search_cockpit.facts.permissions import PermissionService
from job_search_cockpit.readiness.service import ReadinessService
from job_search_cockpit.web.security import LaunchSession

router = APIRouter()


@router.get("/launch")
def launch(request: Request, token: str = "") -> Response:
    launch_session: LaunchSession = request.app.state.launch_session
    if not launch_session.exchange(token, time.monotonic()):
        return PlainTextResponse("Invalid or expired launch token.", status_code=401)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        "cockpit_session",
        launch_session.session_cookie,
        httponly=True,
        samesite="strict",
        path="/",
    )
    return response


@router.get("/health")
def health() -> PlainTextResponse:
    return PlainTextResponse("ok")


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> Response:
    services = request.app.state.prepared.services
    if isinstance(services.permission_service, PermissionService):
        services.permission_service.expire_due(request.app.state.now())
    readiness = services.readiness_service
    if not isinstance(readiness, ReadinessService):
        raise RuntimeError("Readiness service is unavailable.")
    report = readiness.report()
    response: Response = request.app.state.templates.TemplateResponse(
        request,
        "home.html",
        {
            "report": report,
            "csrf_token": request.app.state.launch_session.csrf_token,
        },
    )
    return response
