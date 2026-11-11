from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from sqlalchemy import func, select

from job_search_cockpit.phase1_contract.service import Phase1ContractUnavailable
from job_search_cockpit.phase1_contract.snapshots import Phase1DisclosureEpochRequest
from job_search_cockpit.phase2.activation import Phase2ActivationService
from job_search_cockpit.phase2.assessment_types import EvidenceRelation
from job_search_cockpit.phase2.candidates import (
    CandidateReview,
    CandidateWorkflowUnavailable,
    LocalManualMappingLaunch,
    LocalManualMappingSelection,
)
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
from job_search_cockpit.storage.models import (
    Phase1FactDisclosureAuthorization,
    Phase1FactDisclosureAuthorizationFact,
    Phase1FactDisclosureAuthorizationTaxonomy,
    Phase1MatchingDisclosureEpoch,
)

router = APIRouter()


@dataclass(frozen=True, slots=True)
class DisclosureBudgetView:
    epoch_number: int
    policy_generation: int
    disclosed_fact_count: int
    disclosed_taxonomy_count: int
    fact_budget: int = 64
    taxonomy_budget: int = 32


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
    parameters = request.query_params
    state_values = parameters.getlist("state")
    code_values = parameters.getlist("code")
    error_values = parameters.getlist("error")
    if (
        runtime is None
        or runtime.drive_backup_service is None
        or set(parameters) - {"state", "code", "error"}
        or len(state_values) != 1
        or len(code_values) + len(error_values) != 1
    ):
        return PlainTextResponse("Google authorization is unavailable.", status_code=400)
    state = _bounded(state_values[0], 120)
    if not state:
        return PlainTextResponse("Google authorization is unavailable.", status_code=400)
    try:
        if code_values:
            code = _bounded(code_values[0], 4096)
            if not code:
                return PlainTextResponse("Google authorization is unavailable.", status_code=400)
            runtime.drive_backup_service.complete_authorization(
                state=state,
                code=code,
                session_id=request.app.state.launch_session.session_id,
            )
        elif error_values == ["access_denied"]:
            runtime.drive_backup_service.deny_authorization(
                state=state,
                reason_code="access_denied",
                session_id=request.app.state.launch_session.session_id,
            )
            return PlainTextResponse("Google authorization was cancelled safely.")
        else:
            return PlainTextResponse("Google authorization is unavailable.", status_code=400)
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


@router.post("/phase-2/drive-backups/{operation_id}/retry")
async def retry_drive_backup(request: Request, operation_id: str) -> Response:
    form = await request.form()
    if not request.app.state.launch_session.valid_csrf(form.get("csrf_token")):
        return PlainTextResponse("Invalid request token.", status_code=403)
    runtime = _runtime(request)
    operation_id = _bounded(operation_id, 120)
    if runtime is None or runtime.drive_backup_service is None or not operation_id:
        return PlainTextResponse("Drive backup is unavailable.", status_code=400)
    try:
        runtime.drive_backup_service.retry_backup(operation_id)
    except ValueError:
        return PlainTextResponse("Drive backup is unavailable.", status_code=400)
    return RedirectResponse("/phase-2/review", status_code=303)


@router.get("/phase-2", response_class=HTMLResponse)
def activation_page(request: Request) -> Response:
    service = _activation_service(request)
    if service is None:
        context = {"state": "inactive", "blocker": "Phase II activation is unavailable."}
    else:
        view = service.validate_current()
        context = {
            "state": view.state,
            "blocker": service.activation_blocker() or "",
            "suspension_reason": view.reason if view.state == "suspended" else "",
        }
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
    candidates, phase1_unavailable = _review_candidates(runtime)
    error = request.query_params.get("error") or getattr(request.app.state, "launch_error", None)
    if hasattr(request.app.state, "launch_error"):
        request.app.state.launch_error = None
    response: Response = request.app.state.templates.TemplateResponse(
        request,
        "phase2_local_review.html",
        {
            "csrf_token": request.app.state.launch_session.csrf_token,
            "discovery_status": status,
            "candidates": candidates,
            "error": error,
            "phase1_unavailable": phase1_unavailable,
            "mapped_job_revision_ids": (
                runtime.locally_mapped_job_revision_ids if runtime is not None else set()
            ),
            "verified_resume_job_ids": {
                candidate.job_revision_id: job_id
                for candidate in candidates
                if runtime is not None
                if (job_id := runtime.verified_resume_job_id(candidate.job_revision_id))
                is not None
            },
            "candidate_source_urls": (
                runtime.current_candidate_source_urls() if runtime is not None else {}
            ),
        },
    )
    return response


@router.post("/phase-2/discovery-runs")
async def run_manual_discovery(request: Request) -> Response:
    form = await request.form()
    if not request.app.state.launch_session.valid_csrf(form.get("csrf_token")):
        return PlainTextResponse("Invalid request token.", status_code=403)
    runtime = _runtime(request)
    if runtime is not None:
        # The service owns its approved providers, query, caps, and spend limits.
        # This route accepts no browser-controlled discovery parameters.
        with suppress(Phase2ActivationUnavailable, ValueError):
            runtime.discovery_service.run_micro_pilot()
    return RedirectResponse("/phase-2/review", status_code=303)


def _current_candidates(runtime: Phase2Runtime | None) -> tuple[CandidateReview, ...]:
    return _review_candidates(runtime)[0]


def _review_candidates(
    runtime: Phase2Runtime | None,
) -> tuple[tuple[CandidateReview, ...], bool]:
    if runtime is None:
        return (), False
    try:
        return runtime.candidate_workflow_service.current_candidates(), False
    except Phase1ContractUnavailable:
        return (), True
    except (Phase2ActivationUnavailable, ValueError):
        return (), False


@router.post("/phase-2/mapping-attempts")
async def begin_mapping(request: Request) -> Response:
    form = await request.form()
    if not request.app.state.launch_session.valid_csrf(form.get("csrf_token")):
        return PlainTextResponse("Invalid request token.", status_code=403)
    runtime = _runtime(request)
    revision_id = _bounded(form.get("job_revision_id"), 120)
    candidate = next(
        (item for item in _current_candidates(runtime) if item.job_revision_id == revision_id), None
    )
    if runtime is None or candidate is None or candidate.gate_result.value != "pass":
        return RedirectResponse("/phase-2/review", status_code=303)
    try:
        launch = runtime.candidate_workflow_service.begin_local_manual_mapping(
            revision_id, candidate.selected_location_path or ""
        )
    except (CandidateWorkflowUnavailable, Phase2ActivationUnavailable, ValueError, IndexError) as error:
        request.app.state.launch_error = str(error)
        return RedirectResponse("/phase-2/review", status_code=303)
    runtime.remember_local_manual_mapping(launch)
    return RedirectResponse(f"/phase-2/mapping-attempts/{launch.attempt_id}", status_code=303)


@router.get("/phase-2/mapping-attempts/{attempt_id}", response_class=HTMLResponse)
def mapping_page(request: Request, attempt_id: str) -> Response:
    runtime = _runtime(request)
    launch = runtime.local_manual_mapping(_bounded(attempt_id, 120)) if runtime else None
    if runtime is None or launch is None:
        return RedirectResponse("/phase-2/review", status_code=303)
    response: Response = request.app.state.templates.TemplateResponse(
        request,
        "phase2_mapping.html",
        {
            "csrf_token": request.app.state.launch_session.csrf_token,
            "launch": launch,
            "mapping_requirements": _mapping_requirement_views(launch),
        },
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/phase-2/mapping-attempts/{attempt_id}")
async def publish_mapping(request: Request, attempt_id: str) -> Response:
    form = await request.form()
    if not request.app.state.launch_session.valid_csrf(form.get("csrf_token")):
        return PlainTextResponse("Invalid request token.", status_code=403)
    runtime = _runtime(request)
    launch = runtime.local_manual_mapping(_bounded(attempt_id, 120)) if runtime else None
    if runtime is None or launch is None:
        return RedirectResponse("/phase-2/review", status_code=303)
    try:
        selections = _mapping_selections(launch, form)
        runtime.candidate_workflow_service.publish_local_manual_mapping(launch, selections)
    except (CandidateWorkflowUnavailable, Phase2ActivationUnavailable, ValueError):
        return RedirectResponse(f"/phase-2/mapping-attempts/{launch.attempt_id}", status_code=303)
    runtime.forget_local_manual_mapping(launch.attempt_id)
    return RedirectResponse("/phase-2/review", status_code=303)


def _mapping_selections(
    launch: LocalManualMappingLaunch, form: object
) -> tuple[LocalManualMappingSelection, ...]:
    values = cast("dict[str, object]", form)
    selections: list[LocalManualMappingSelection] = []
    for requirement in launch.requirements:
        key = requirement.requirement_id
        relation = EvidenceRelation(str(values.get(f"relation:{key}", "")))
        reason = _bounded(values.get(f"reason:{key}"), 120)
        choice_index = _bounded(values.get(f"choice:{key}"), 8)
        if relation is EvidenceRelation.NONE:
            if choice_index:
                raise ValueError("No-evidence mappings cannot select a fact.")
            selections.append(LocalManualMappingSelection(key, relation, reason))
            continue
        if not choice_index.isdecimal():
            raise ValueError("A supported mapping must select an approved fact.")
        index = int(choice_index)
        if not 0 <= index < len(launch.choices):
            raise ValueError("The approved fact selection is unavailable.")
        choice = launch.choices[index]
        selections.append(
            LocalManualMappingSelection(key, relation, reason, choice[1], choice[2], choice[3])
        )
    return tuple(selections)


def _mapping_requirement_views(launch: LocalManualMappingLaunch) -> tuple[dict[str, object], ...]:
    public_text = dict(getattr(launch, "public_requirement_texts", ()))
    edges = {
        (edge.requirement_id, edge.claim_id)
        for edge in launch.manifest.edges
    }
    return tuple(
        {
            "requirement": requirement,
            "text": public_text.get(requirement.requirement_id, ""),
            "citation": (
                f"{requirement.source_span_id} · characters "
                f"{requirement.start_offset}-{requirement.end_offset}"
            ),
            "choices": tuple(
                (index, choice[4])
                for index, choice in enumerate(launch.choices)
                if (requirement.requirement_id, choice[1]) in edges
            ),
        }
        for requirement in launch.requirements
    )


@router.post("/phase-2/disclosure-epochs")
async def renew_disclosure_epoch(request: Request) -> Response:
    form = await request.form()
    if not request.app.state.launch_session.valid_csrf(form.get("csrf_token")):
        return PlainTextResponse("Invalid request token.", status_code=403)
    runtime = _runtime(request)
    if runtime is not None:
        with suppress(Phase1ContractUnavailable, ValueError):
            runtime.phase1_port.start_new_matching_disclosure_epoch(
                Phase1DisclosureEpochRequest(
                    reason=_bounded(form.get("reason"), 500),
                    confirmation=str(form.get("confirmation", "")),
                )
            )
    return RedirectResponse("/phase-2/review", status_code=303)


@router.get("/phase-2/disclosure-budget", response_class=HTMLResponse)
def disclosure_budget_page(request: Request) -> Response:
    view = _disclosure_budget_view(request)
    response: Response = request.app.state.templates.TemplateResponse(
        request,
        "phase2_disclosure_budget.html",
        {"csrf_token": request.app.state.launch_session.csrf_token, "disclosure_budget": view},
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _disclosure_budget_view(request: Request) -> DisclosureBudgetView | None:
    coordinator = request.app.state.prepared.coordinator
    with coordinator._session_factory() as session:
        epoch = session.scalar(
            select(Phase1MatchingDisclosureEpoch).order_by(
                Phase1MatchingDisclosureEpoch.epoch_number.desc()
            )
        )
        if epoch is None:
            return None
        authorization_ids = select(Phase1FactDisclosureAuthorization.id).where(
            Phase1FactDisclosureAuthorization.disclosure_budget_epoch == epoch.epoch_number
        )
        fact_count = int(
            session.scalar(
                select(func.count(func.distinct(Phase1FactDisclosureAuthorizationFact.claim_id))).where(
                    Phase1FactDisclosureAuthorizationFact.authorization_id.in_(authorization_ids)
                )
            )
            or 0
        )
        taxonomy_count = int(
            session.scalar(
                select(
                    func.count(func.distinct(Phase1FactDisclosureAuthorizationTaxonomy.taxonomy_id))
                ).where(Phase1FactDisclosureAuthorizationTaxonomy.authorization_id.in_(authorization_ids))
            )
            or 0
        )
    return DisclosureBudgetView(
        epoch.epoch_number, epoch.policy_generation, fact_count, taxonomy_count
    )


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
    drive_backup_view = None
    if artifact is not None and runtime.drive_backup_service is not None:
        with suppress(ValueError):
            drive_backup_view = runtime.drive_backup_service.view_for_artifact(artifact.artifact_id)
    return _resume_page(request, review, artifact, drive_backup_view=drive_backup_view)


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
    drive_backup_view: object | None = None,
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
            "drive_backup_view": drive_backup_view,
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
        revision_id = _bounded(form.get("job_revision_id"), 120)
        candidate = next(
            (item for item in _current_candidates(runtime) if item.job_revision_id == revision_id),
            None,
        )
        if (
            candidate is not None
            and candidate.gate_result.value == "pass"
            and revision_id in runtime.locally_mapped_job_revision_ids
        ):
            with suppress(Phase2ActivationUnavailable, ResumePreparationError, ValueError):
                runtime.verified_job_authorization_service.verify(
                    VerifyCandidateCommand(
                        job_revision_id=revision_id,
                        selected_location_path=candidate.selected_location_path or "",
                        actor="Varun",
                        reason=_bounded(form.get("reason"), 500),
                        confirmation=str(form.get("confirmation", "")),
                        eligibility="eligible",
                    )
                )
    return RedirectResponse("/phase-2/review", status_code=303)
