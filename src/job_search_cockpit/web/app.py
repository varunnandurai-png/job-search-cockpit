from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import RequestResponseEndpoint

from job_search_cockpit.config import Settings
from job_search_cockpit.ports import PreparedVault
from job_search_cockpit.storage.mutation import MutationCoordinator
from job_search_cockpit.web.routes import history, home, imports, review, search_profile
from job_search_cockpit.web.security import LaunchSession


def _secured(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self'; img-src 'self'; "
        "script-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    )
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def create_app(
    settings: Settings,
    prepared: PreparedVault,
    launch_session: LaunchSession,
    active_port: int,
) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    template_dir = Path(__file__).parent / "templates"
    templates = Jinja2Templates(directory=template_dir)
    if not templates.env.autoescape:
        raise RuntimeError("Jinja autoescape must remain enabled.")
    app.state.settings = settings
    app.state.prepared = prepared
    app.state.launch_session = launch_session
    app.state.active_port = active_port
    app.state.templates = templates
    app.state.now = lambda: datetime.now(UTC)

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.middleware("http")
    async def protect_local_session(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        expected_host = f"127.0.0.1:{active_port}"
        if request.headers.get("host") != expected_host:
            return _secured(PlainTextResponse("Invalid local host.", status_code=400))
        if request.method not in {"GET", "HEAD", "POST"}:
            return _secured(PlainTextResponse("Method not allowed.", status_code=405))
        if request.headers.get("upgrade", "").lower() == "websocket":
            return _secured(PlainTextResponse("WebSocket access is disabled.", status_code=400))
        if request.url.path != "/launch" and not launch_session.valid_cookie(
            request.cookies.get("cockpit_session")
        ):
            return _secured(PlainTextResponse("Launch session required.", status_code=401))
        if request.method == "POST":
            origin = request.headers.get("origin", "")
            parsed_origin = urlsplit(origin)
            exact_origin = (
                parsed_origin.scheme == "http"
                and parsed_origin.hostname == "127.0.0.1"
                and parsed_origin.port == active_port
            )
            same_origin_navigation = (
                origin == "null"
                and request.headers.get("sec-fetch-site") == "same-origin"
                and request.headers.get("sec-fetch-mode") == "navigate"
            )
            if not (exact_origin or same_origin_navigation):
                return _secured(PlainTextResponse("Invalid request origin.", status_code=403))
        coordinator = prepared.coordinator
        if not isinstance(coordinator, MutationCoordinator):
            return _secured(PlainTextResponse("Vault coordinator unavailable.", status_code=503))
        await run_in_threadpool(coordinator.begin_request)
        try:
            response = await call_next(request)
            return _secured(response)
        finally:
            await run_in_threadpool(coordinator.end_request)

    app.include_router(home.router)
    app.include_router(imports.router)
    app.include_router(review.router)
    app.include_router(search_profile.router)
    app.include_router(history.router)
    return app
