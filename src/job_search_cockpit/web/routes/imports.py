from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response

from job_search_cockpit.imports.service import ImportPreview, ImportService, PreviewRejected
from job_search_cockpit.web.security import LaunchSession

router = APIRouter(prefix="/imports")

SOURCE_LABELS = {
    "assessment": "Job search assessment",
    "profile_json": "Structured profile",
    "master_profile": "Master career profile",
    "resume_workflow": "Resume workflow",
}


def _authorized(request: Request, csrf_token: str) -> bool:
    launch: LaunchSession = request.app.state.launch_session
    return launch.valid_csrf(csrf_token)


def _import_service(request: Request) -> ImportService:
    service = request.app.state.prepared.services.import_service
    if not isinstance(service, ImportService):
        raise RuntimeError("Import service is unavailable.")
    return service


@router.post("/preview", response_class=HTMLResponse)
def preview_import(request: Request, csrf_token: str = Form("")) -> Response:
    if not _authorized(request, csrf_token):
        return PlainTextResponse("Invalid CSRF token.", status_code=403)
    launch: LaunchSession = request.app.state.launch_session
    preview: ImportPreview = _import_service(request).preview(
        launch.session_id, request.app.state.now()
    )
    response: Response = request.app.state.templates.TemplateResponse(
        request,
        "import_preview.html",
        {
            "preview": preview,
            "source_labels": SOURCE_LABELS,
            "csrf_token": launch.csrf_token,
        },
    )
    response.headers["X-Preview-ID"] = preview.id
    return response


@router.post("/apply")
def apply_import(
    request: Request,
    csrf_token: str = Form(""),
    preview_id: str = Form(""),
    confirm_incomplete: bool = Form(False),
) -> Response:
    if not _authorized(request, csrf_token):
        return PlainTextResponse("Invalid CSRF token.", status_code=403)
    launch: LaunchSession = request.app.state.launch_session
    try:
        _import_service(request).apply(
            preview_id,
            launch.session_id,
            request.app.state.now(),
            confirm_incomplete=confirm_incomplete,
        )
    except PreviewRejected as error:
        return PlainTextResponse(str(error), status_code=409)
    return RedirectResponse("/", status_code=303)
