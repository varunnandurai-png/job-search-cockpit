import json

from fastapi import APIRouter, Form, Request
from fastapi.responses import PlainTextResponse, RedirectResponse, Response
from pydantic import ValidationError

from job_search_cockpit.search_profile.catalog import SearchProfilePayload
from job_search_cockpit.search_profile.service import (
    ProfileConfirmationError,
    ProfileVersionConflict,
    confirm_profile_change,
    get_active_profile,
)
from job_search_cockpit.storage.database import session_factory_for
from job_search_cockpit.storage.models import SearchProfileVersion
from job_search_cockpit.storage.mutation import MutationCoordinator
from job_search_cockpit.web.security import LaunchSession

router = APIRouter(prefix="/search-profile")


def _coordinator(request: Request) -> MutationCoordinator:
    coordinator = request.app.state.prepared.coordinator
    if not isinstance(coordinator, MutationCoordinator):
        raise RuntimeError("Mutation coordinator is unavailable.")
    return coordinator


def _context(request: Request, error: str = "", submitted_json: str = "") -> dict[str, object]:
    factory = session_factory_for(_coordinator(request).engine)
    with factory() as session:
        active = get_active_profile(session)
        versions = tuple(
            session.query(SearchProfileVersion)
            .order_by(SearchProfileVersion.version_number.desc())
            .all()
        )
        payload = SearchProfilePayload.model_validate(active.payload_json)
    return {
        "active": active,
        "versions": versions,
        "profile": payload,
        "payload_json": submitted_json or payload.model_dump_json(indent=2),
        "csrf_token": request.app.state.launch_session.csrf_token,
        "error": error,
    }


def _render(
    request: Request, *, error: str = "", submitted_json: str = "", status_code: int = 200
) -> Response:
    response: Response = request.app.state.templates.TemplateResponse(
        request,
        "search_profile.html",
        _context(request, error, submitted_json),
        status_code=status_code,
    )
    return response


@router.get("")
def show_search_profile(request: Request) -> Response:
    return _render(request)


@router.post("/new-version")
def create_profile_version(
    request: Request,
    payload_json: str = Form(""),
    reason: str = Form(""),
    confirmation: str = Form(""),
    expected_active_version: int = Form(0),
    expected_diff_digest: str = Form(""),
    csrf_token: str = Form(""),
) -> Response:
    launch: LaunchSession = request.app.state.launch_session
    if not launch.valid_csrf(csrf_token):
        return PlainTextResponse("Invalid CSRF token.", status_code=403)
    try:
        raw = json.loads(payload_json)
        profile = SearchProfilePayload.model_validate(raw)
        confirm_profile_change(
            _coordinator(request),
            profile,
            reason,
            confirmation,
            expected_active_version,
            expected_diff_digest,
        )
    except ProfileVersionConflict as error:
        return _render(request, error=str(error), submitted_json=payload_json, status_code=409)
    except (ProfileConfirmationError, ValidationError, json.JSONDecodeError) as error:
        return _render(request, error=str(error), submitted_json=payload_json, status_code=422)
    return RedirectResponse("/search-profile", status_code=303)
