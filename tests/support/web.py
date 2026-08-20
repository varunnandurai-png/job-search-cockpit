from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from http.cookies import SimpleCookie
from typing import Any

from fastapi.testclient import TestClient

from job_search_cockpit.config import Settings
from job_search_cockpit.facts.permissions import NamedUseService, PermissionService
from job_search_cockpit.facts.review import ReviewService
from job_search_cockpit.imports.service import ImportService
from job_search_cockpit.ports import PreparedVault, ServiceBundle
from job_search_cockpit.readiness.service import ReadinessService
from job_search_cockpit.storage.database import create_engine_for, upgrade_database
from job_search_cockpit.storage.mutation import AppInstanceLock, MutationCoordinator
from job_search_cockpit.web.app import create_app
from job_search_cockpit.web.security import LaunchSession


@dataclass(frozen=True, slots=True)
class ParsedCookie:
    httponly: bool
    samesite: str
    path: str


@contextmanager
def build_test_app(
    settings: Settings, *, launch: LaunchSession | None = None
) -> Iterator[tuple[LaunchSession, TestClient]]:
    upgrade_database(f"sqlite:///{settings.database_path}")
    engine = create_engine_for(settings)
    lock = AppInstanceLock.acquire(settings)
    coordinator = MutationCoordinator(settings, engine, lock)
    launch = launch or LaunchSession.fresh()
    prepared = PreparedVault(
        lock,
        coordinator,
        engine,
        ServiceBundle(
            import_service=ImportService(settings, coordinator),
            review_service=ReviewService(coordinator),
            readiness_service=ReadinessService(coordinator),
            permission_service=PermissionService(coordinator),
            named_use_service=NamedUseService(coordinator),
        ),
    )
    app = create_app(settings, prepared, launch, 8765)
    try:
        with TestClient(app, base_url="http://127.0.0.1:8765") as client:
            yield launch, client
    finally:
        coordinator.dispose()
        lock.release()


def parse_set_cookie(header: str) -> ParsedCookie:
    cookie = SimpleCookie()
    cookie.load(header)
    morsel = next(iter(cookie.values()))
    return ParsedCookie(
        httponly=bool(morsel["httponly"]),
        samesite=morsel["samesite"],
        path=morsel["path"],
    )


class AuthenticatedClient:
    def __init__(self, client: TestClient, csrf: str, origin: str) -> None:
        self.client = client
        self.csrf = csrf
        self.origin = origin

    def get(self, *args: object, **kwargs: object) -> Any:
        return self.client.get(*args, **kwargs)

    def post(self, *args: object, **kwargs: object) -> Any:
        data = dict(kwargs.pop("data", {}) or {})
        data.setdefault("csrf_token", self.csrf)
        kwargs["data"] = data
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.setdefault("origin", self.origin)
        kwargs["headers"] = headers
        return self.client.post(*args, **kwargs)


@contextmanager
def authenticated_test_app(settings: Settings) -> Iterator[AuthenticatedClient]:
    with build_test_app(settings) as (launch, client):
        response = client.get(f"/launch?token={launch.token}")
        assert response.status_code == 200
        yield AuthenticatedClient(client, launch.csrf_token, "http://127.0.0.1:8765")


@dataclass(slots=True)
class RunningApp:
    launch_url: str
    base_url: str
    stop: Any


def assert_accessible_page(page: Any) -> None:
    assert page.locator("main").count() == 1
    assert page.locator("h1").count() == 1
    assert page.locator("[aria-label], label").count() > 0


def assert_readiness_is_false(page: Any) -> None:
    assert "not ready" in page.locator("main").inner_text().lower()


def resolve_all_fixture_reviews(page: Any) -> None:
    while page.get_by_role("link", name="Review next fact").count():
        page.get_by_role("link", name="Review next fact").click()
        page.get_by_role("button", name="Approve fact").click()
