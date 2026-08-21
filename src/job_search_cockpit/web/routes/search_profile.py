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
    profile_diff_digest,
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


def _context(
    request: Request,
    error: str = "",
    submitted_json: str = "",
    submitted_reason: str = "",
    proposed_profile: SearchProfilePayload | None = None,
    proposed_diff_digest: str = "",
) -> dict[str, object]:
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
        "current_payload_json": payload.model_dump_json(indent=2),
        "payload_json": submitted_json or payload.model_dump_json(indent=2),
        "submitted_reason": submitted_reason,
        "proposed_payload_json": (
            proposed_profile.model_dump_json(indent=2) if proposed_profile is not None else ""
        ),
        "proposed_diff_digest": proposed_diff_digest,
        "csrf_token": request.app.state.launch_session.csrf_token,
        "error": error,
    }


def _render(
    request: Request,
    *,
    error: str = "",
    submitted_json: str = "",
    submitted_reason: str = "",
    proposed_profile: SearchProfilePayload | None = None,
    proposed_diff_digest: str = "",
    status_code: int = 200,
) -> Response:
    response: Response = request.app.state.templates.TemplateResponse(
        request,
        "search_profile.html",
        _context(
            request,
            error,
            submitted_json,
            submitted_reason,
            proposed_profile,
            proposed_diff_digest,
        ),
        status_code=status_code,
    )
    return response


@router.get("")
def show_search_profile(request: Request) -> Response:
    return _render(request)


@router.post("/preview")
def preview_profile_version(
    request: Request,
    payload_json: str = Form(""),
    reason: str = Form(""),
    expected_active_version: int = Form(0),
    csrf_token: str = Form(""),
) -> Response:
    launch: LaunchSession = request.app.state.launch_session
    if not launch.valid_csrf(csrf_token):
        return PlainTextResponse("Invalid CSRF token.", status_code=403)
    try:
        raw = json.loads(payload_json)
        proposed = SearchProfilePayload.model_validate(raw)
        if not reason.strip():
            raise ProfileConfirmationError("A reason is required to review a profile change.")
        factory = session_factory_for(_coordinator(request).engine)
        with factory() as session:
            active = get_active_profile(session)
            if active.version_number != expected_active_version:
                raise ProfileVersionConflict(
                    "The active target profile changed. Review it and try again."
                )
            current = SearchProfilePayload.model_validate(active.payload_json)
        digest = profile_diff_digest(current, proposed)
    except ProfileVersionConflict as error:
        return _render(
            request,
            error=str(error),
            submitted_json=payload_json,
            submitted_reason=reason,
            status_code=409,
        )
    except (ProfileConfirmationError, ValidationError, json.JSONDecodeError) as error:
        return _render(
            request,
            error=str(error),
            submitted_json=payload_json,
            submitted_reason=reason,
            status_code=422,
        )
    return _render(
        request,
        submitted_json=proposed.model_dump_json(indent=2),
        submitted_reason=reason.strip(),
        proposed_profile=proposed,
        proposed_diff_digest=digest,
    )


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
        return _render(
            request,
            error=str(error),
            submitted_json=payload_json,
            submitted_reason=reason,
            status_code=409,
        )
    except (ProfileConfirmationError, ValidationError, json.JSONDecodeError) as error:
        return _render(
            request,
            error=str(error),
            submitted_json=payload_json,
            submitted_reason=reason,
            status_code=422,
        )
    return RedirectResponse("/search-profile", status_code=303)
