import re
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import PlainTextResponse, RedirectResponse, Response
from sqlalchemy import select

from job_search_cockpit.facts.conflicts import (
    ConflictResolutionError,
    ResolveConflictCommand,
    resolve_conflict,
)
from job_search_cockpit.facts.permissions import (
    NamedUseService,
    PermissionError,
    PermissionService,
)
from job_search_cockpit.facts.repository import FactRepository
from job_search_cockpit.facts.review import (
    BulkReviewItem,
    ClaimVersionConflict,
    ReviewError,
    ReviewService,
)
from job_search_cockpit.facts.types import Sensitivity
from job_search_cockpit.storage.database import session_factory_for
from job_search_cockpit.storage.models import (
    Claim,
    ClaimEvidence,
    ClaimRevision,
    ConfidentialPermissionEvent,
    ConflictGroup,
    ConflictMember,
    Decision,
)
from job_search_cockpit.storage.mutation import MutationCoordinator
from job_search_cockpit.web.security import LaunchSession

router = APIRouter()

FILTERS = (
    ("needs_attention", "Needs attention"),
    ("conflicts", "Conflicts"),
    ("numbers", "Numbers"),
    ("dates", "Dates"),
    ("titles", "Titles"),
    ("sensitivity_unreviewed", "Confidentiality not reviewed"),
    ("confidential", "Confidential"),
    ("stale", "Stale"),
    ("low_risk", "Low risk"),
)


def _services(request: Request) -> tuple[ReviewService, PermissionService, NamedUseService]:
    bundle = request.app.state.prepared.services
    if not isinstance(bundle.review_service, ReviewService):
        raise RuntimeError("Review service is unavailable.")
    if not isinstance(bundle.permission_service, PermissionService):
        raise RuntimeError("Permission service is unavailable.")
    if not isinstance(bundle.named_use_service, NamedUseService):
        raise RuntimeError("Named-use service is unavailable.")
    return bundle.review_service, bundle.permission_service, bundle.named_use_service


def _coordinator(request: Request) -> MutationCoordinator:
    coordinator = request.app.state.prepared.coordinator
    if not isinstance(coordinator, MutationCoordinator):
        raise RuntimeError("Mutation coordinator is unavailable.")
    return coordinator


def _valid_csrf(request: Request, csrf_token: str) -> bool:
    launch: LaunchSession = request.app.state.launch_session
    return launch.valid_csrf(csrf_token)


def _redirect_fact(claim_id: str) -> RedirectResponse:
    return RedirectResponse(f"/review/{claim_id}", status_code=303)


def _parse_date(value: str) -> date | None:
    return date.fromisoformat(value) if value.strip() else None


def _risk_details(claim: Claim, revision: ClaimRevision, conflict: bool) -> tuple[int, list[str]]:
    reasons: list[str] = []
    unresolved = claim.status.value == "unresolved"
    if conflict:
        reasons.append("Sources disagree")
    if claim.sensitivity == Sensitivity.UNREVIEWED:
        reasons.append("Confidentiality not reviewed")
    if claim.sensitivity == Sensitivity.CONFIDENTIAL:
        reasons.append("Confidential")
    if unresolved and re.search(r"\d", revision.display_value):
        reasons.append("Number requires individual review")
    if unresolved and (claim.category == "dates" or claim.canonical_key.endswith(".dates")):
        reasons.append("Date requires individual review")
    if unresolved and (claim.category == "title" or claim.canonical_key.endswith(".title")):
        reasons.append("Title requires individual review")
    if unresolved and ("team" in claim.canonical_key or "team" in revision.display_value.lower()):
        reasons.append("Team scope requires individual review")
    if claim.stale:
        reasons.append("Source is stale")
    if not reasons and unresolved:
        reasons.append("Review required")
    order = {
        "Sources disagree": 0,
        "Confidentiality not reviewed": 1,
        "Confidential": 2,
        "Number requires individual review": 3,
        "Date requires individual review": 4,
        "Title requires individual review": 5,
        "Team scope requires individual review": 6,
        "Source is stale": 7,
        "Review required": 8,
    }
    return min((order[reason] for reason in reasons), default=9), reasons


@router.get("/review")
def review_queue(request: Request, filter: str = "needs_attention") -> Response:
    factory = session_factory_for(_coordinator(request).engine)
    with factory() as session:
        claims = FactRepository(session).queue()
        conflict_claim_ids = set(
            session.scalars(
                select(ConflictMember.claim_id)
                .join(ConflictGroup)
                .where(ConflictGroup.status == "open")
            )
        )
        rows: list[dict[str, Any]] = []
        for claim in claims:
            revision = session.get(ClaimRevision, claim.active_revision_id)
            if revision is None:
                continue
            priority, reasons = _risk_details(claim, revision, claim.id in conflict_claim_ids)
            matches = {
                "needs_attention": bool(reasons),
                "conflicts": "Sources disagree" in reasons,
                "numbers": "Number requires individual review" in reasons,
                "dates": "Date requires individual review" in reasons,
                "titles": "Title requires individual review" in reasons,
                "sensitivity_unreviewed": "Confidentiality not reviewed" in reasons,
                "confidential": "Confidential" in reasons,
                "stale": "Source is stale" in reasons,
                "low_risk": reasons == ["Review required"],
            }
            if matches.get(filter, matches["needs_attention"]):
                rows.append(
                    {"claim": claim, "revision": revision, "reasons": reasons, "priority": priority}
                )
        rows.sort(key=lambda row: (row["priority"], row["claim"].canonical_key))
        response: Response = request.app.state.templates.TemplateResponse(
            request,
            "review_queue.html",
            {
                "rows": rows,
                "filters": FILTERS,
                "active_filter": filter,
                "csrf_token": request.app.state.launch_session.csrf_token,
            },
        )
        return response


def _fact_context(request: Request, claim_id: str) -> dict[str, Any] | None:
    factory = session_factory_for(_coordinator(request).engine)
    with factory() as session:
        detail = FactRepository(session).get(claim_id)
        if detail is None:
            return None
        group = session.scalar(
            select(ConflictGroup)
            .join(ConflictMember)
            .where(ConflictMember.claim_id == claim_id, ConflictGroup.status == "open")
        )
        conflict_rows: list[dict[str, Any]] = []
        if group is not None:
            members = session.scalars(
                select(ConflictMember).where(ConflictMember.conflict_group_id == group.id)
            )
            for member in members:
                revision = session.get(ClaimRevision, member.revision_id)
                if revision is None:
                    continue
                evidence = tuple(
                    session.scalars(
                        select(ClaimEvidence).where(ClaimEvidence.revision_id == revision.id)
                    )
                )
                conflict_rows.append({"member": member, "revision": revision, "evidence": evidence})
        decisions = tuple(
            session.scalars(
                select(Decision)
                .where(Decision.claim_id == claim_id)
                .order_by(Decision.created_at.desc())
            )
        )
        evidence_by_revision = {
            revision.id: tuple(item for item in detail.evidence if item.revision_id == revision.id)
            for revision in detail.revisions
        }
        return {
            "claim": detail.claim,
            "revisions": detail.revisions,
            "evidence_by_revision": evidence_by_revision,
            "group": group,
            "conflict_rows": conflict_rows,
            "decisions": decisions,
            "csrf_token": request.app.state.launch_session.csrf_token,
        }


def _render_fact(
    request: Request,
    claim_id: str,
    *,
    error: str = "",
    submitted_value: str = "",
    status_code: int = 200,
) -> Response:
    context = _fact_context(request, claim_id)
    if context is None:
        return PlainTextResponse("Fact not found.", status_code=404)
    context.update({"error": error, "submitted_value": submitted_value})
    response: Response = request.app.state.templates.TemplateResponse(
        request, "review_fact.html", context, status_code=status_code
    )
    return response


@router.get("/review/{claim_id}")
def review_fact(request: Request, claim_id: str) -> Response:
    return _render_fact(request, claim_id)


def _review_error(
    request: Request, claim_id: str, error: ReviewError, submitted_value: str = ""
) -> Response:
    status = 409 if isinstance(error, ClaimVersionConflict) else 422
    return _render_fact(
        request,
        claim_id,
        error=str(error),
        submitted_value=submitted_value,
        status_code=status,
    )


@router.post("/review/{claim_id}/approve")
def approve_fact(
    request: Request,
    claim_id: str,
    revision_id: str = Form(""),
    expected_version: int = Form(0),
    csrf_token: str = Form(""),
) -> Response:
    if not _valid_csrf(request, csrf_token):
        return PlainTextResponse("Invalid CSRF token.", status_code=403)
    try:
        _services(request)[0].approve(claim_id, revision_id, expected_version)
    except ReviewError as error:
        return _review_error(request, claim_id, error)
    return _redirect_fact(claim_id)


@router.post("/review/{claim_id}/correct")
def correct_fact(
    request: Request,
    claim_id: str,
    display_value: str = Form(""),
    employer_key: str = Form(""),
    period_start: str = Form(""),
    period_end: str = Form(""),
    expected_version: int = Form(0),
    reason: str = Form(""),
    csrf_token: str = Form(""),
) -> Response:
    if not _valid_csrf(request, csrf_token):
        return PlainTextResponse("Invalid CSRF token.", status_code=403)
    try:
        _services(request)[0].correct(
            claim_id,
            {"text": display_value},
            display_value,
            employer_key or None,
            _parse_date(period_start),
            _parse_date(period_end),
            expected_version,
            reason,
        )
    except (ReviewError, ValueError) as error:
        review_error = error if isinstance(error, ReviewError) else ReviewError(str(error))
        return _review_error(request, claim_id, review_error, display_value)
    return _redirect_fact(claim_id)


@router.post("/review/{claim_id}/confirm-corrected-support")
def confirm_support(
    request: Request,
    claim_id: str,
    revision_id: str = Form(""),
    expected_version: int = Form(0),
    confirmation: str = Form(""),
    reason: str = Form(""),
    csrf_token: str = Form(""),
) -> Response:
    if not _valid_csrf(request, csrf_token):
        return PlainTextResponse("Invalid CSRF token.", status_code=403)
    try:
        _services(request)[0].confirm_corrected_support(
            claim_id, revision_id, expected_version, "Varun", confirmation, reason
        )
    except ReviewError as error:
        return _review_error(request, claim_id, error)
    return _redirect_fact(claim_id)


@router.post("/review/{claim_id}/reject")
def reject_fact(
    request: Request,
    claim_id: str,
    expected_version: int = Form(0),
    reason: str = Form(""),
    csrf_token: str = Form(""),
) -> Response:
    if not _valid_csrf(request, csrf_token):
        return PlainTextResponse("Invalid CSRF token.", status_code=403)
    try:
        _services(request)[0].reject(claim_id, expected_version, reason)
    except ReviewError as error:
        return _review_error(request, claim_id, error)
    return _redirect_fact(claim_id)


@router.post("/review/{claim_id}/revert")
def revert_fact(
    request: Request,
    claim_id: str,
    target_decision_id: str = Form(""),
    expected_version: int = Form(0),
    reason: str = Form(""),
    csrf_token: str = Form(""),
) -> Response:
    if not _valid_csrf(request, csrf_token):
        return PlainTextResponse("Invalid CSRF token.", status_code=403)
    try:
        _services(request)[0].revert(claim_id, target_decision_id, expected_version, reason)
    except ReviewError as error:
        return _review_error(request, claim_id, error)
    return _redirect_fact(claim_id)


@router.post("/review/{claim_id}/sensitivity")
def set_sensitivity(
    request: Request,
    claim_id: str,
    sensitivity: str = Form(""),
    expected_version: int = Form(0),
    reason: str = Form(""),
    csrf_token: str = Form(""),
) -> Response:
    if not _valid_csrf(request, csrf_token):
        return PlainTextResponse("Invalid CSRF token.", status_code=403)
    try:
        _services(request)[0].set_sensitivity(
            claim_id, Sensitivity(sensitivity), expected_version, reason
        )
    except (ReviewError, ValueError) as error:
        review_error = (
            error if isinstance(error, ReviewError) else ReviewError("Choose a sensitivity.")
        )
        return _review_error(request, claim_id, review_error)
    return _redirect_fact(claim_id)


@router.post("/review/bulk-approve")
async def bulk_approve(request: Request) -> Response:
    form = await request.form()
    csrf_token = str(form.get("csrf_token", ""))
    if not _valid_csrf(request, csrf_token):
        return PlainTextResponse("Invalid CSRF token.", status_code=403)
    try:
        items = [
            BulkReviewItem(claim_id, revision_id, int(version))
            for encoded in form.getlist("items")
            for claim_id, revision_id, version in [str(encoded).split("|", 2)]
        ]
        _services(request)[0].bulk_approve_low_risk(items)
    except (ReviewError, ValueError) as error:
        return PlainTextResponse(str(error), status_code=409)
    return RedirectResponse("/review", status_code=303)


@router.post("/review/{claim_id}/resolve-conflict")
def resolve_fact_conflict(
    request: Request,
    claim_id: str,
    group_id: str = Form(""),
    selected_revision_id: str = Form(""),
    corrected_display_value: str = Form(""),
    expected_group_version: int = Form(0),
    reason: str = Form(""),
    employer_key: str = Form(""),
    period_start: str = Form(""),
    period_end: str = Form(""),
    csrf_token: str = Form(""),
) -> Response:
    if not _valid_csrf(request, csrf_token):
        return PlainTextResponse("Invalid CSRF token.", status_code=403)
    corrected = corrected_display_value.strip()
    try:
        resolve_conflict(
            _coordinator(request),
            ResolveConflictCommand(
                group_id,
                selected_revision_id or None,
                {"text": corrected} if corrected else None,
                corrected or None,
                expected_group_version,
                reason,
                employer_key or None,
                _parse_date(period_start),
                _parse_date(period_end),
            ),
        )
    except (ConflictResolutionError, ValueError) as error:
        return _render_fact(request, claim_id, error=str(error), status_code=422)
    return _redirect_fact(claim_id)


@router.get("/review/{claim_id}/confidential-use/new")
def new_confidential_use(request: Request, claim_id: str) -> Response:
    context = _fact_context(request, claim_id)
    if context is None:
        return PlainTextResponse("Fact not found.", status_code=404)
    factory = session_factory_for(_coordinator(request).engine)
    with factory() as session:
        context["permission_events"] = tuple(
            session.scalars(
                select(ConfidentialPermissionEvent)
                .where(ConfidentialPermissionEvent.claim_id == claim_id)
                .order_by(ConfidentialPermissionEvent.created_at.desc())
            )
        )
    response: Response = request.app.state.templates.TemplateResponse(
        request, "confidential_permission.html", context
    )
    return response


@router.post("/review/{claim_id}/confidential-use")
def grant_confidential_use(
    request: Request,
    claim_id: str,
    revision_id: str = Form(""),
    purpose_type: str = Form(""),
    external_reference: str = Form(""),
    description: str = Form(""),
    confirmation: str = Form(""),
    expires_at: str = Form(""),
    csrf_token: str = Form(""),
) -> Response:
    if not _valid_csrf(request, csrf_token):
        return PlainTextResponse("Invalid CSRF token.", status_code=403)
    _review, permissions, named_uses = _services(request)
    try:
        named_use = named_uses.create(purpose_type, external_reference, description, "Varun")
        permissions.grant(
            claim_id,
            revision_id,
            named_use.id,
            "Varun",
            confirmation,
            datetime.fromisoformat(expires_at) if expires_at else None,
            0,
        )
    except (PermissionError, ValueError) as error:
        return PlainTextResponse(str(error), status_code=422)
    return RedirectResponse(f"/review/{claim_id}/confidential-use/new", status_code=303)


@router.post("/confidential-use/{permission_event_id}/revoke")
def revoke_confidential_use(
    request: Request,
    permission_event_id: str,
    reason: str = Form(""),
    expected_event_version: int = Form(0),
    csrf_token: str = Form(""),
) -> Response:
    if not _valid_csrf(request, csrf_token):
        return PlainTextResponse("Invalid CSRF token.", status_code=403)
    try:
        event = _services(request)[1].revoke(
            permission_event_id, "Varun", reason, expected_event_version
        )
    except PermissionError as error:
        return PlainTextResponse(str(error), status_code=409)
    return RedirectResponse(f"/review/{event.claim_id}/confidential-use/new", status_code=303)


@router.post("/confidential-use/{permission_event_id}/supersede")
def supersede_confidential_use(
    request: Request,
    permission_event_id: str,
    replacement_named_use_id: str = Form(""),
    confirmation: str = Form(""),
    expires_at: str = Form(""),
    expected_event_version: int = Form(0),
    csrf_token: str = Form(""),
) -> Response:
    if not _valid_csrf(request, csrf_token):
        return PlainTextResponse("Invalid CSRF token.", status_code=403)
    try:
        event = _services(request)[1].supersede(
            permission_event_id,
            replacement_named_use_id,
            "Varun",
            confirmation,
            datetime.fromisoformat(expires_at) if expires_at else None,
            expected_event_version,
        )
    except (PermissionError, ValueError) as error:
        return PlainTextResponse(str(error), status_code=409)
    return RedirectResponse(f"/review/{event.claim_id}/confidential-use/new", status_code=303)
