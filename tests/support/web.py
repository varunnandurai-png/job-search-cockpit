from dataclasses import dataclass
from http.cookies import SimpleCookie
from typing import Any

from fastapi.testclient import TestClient


@dataclass(frozen=True, slots=True)
class ParsedCookie:
    httponly: bool
    samesite: str
    path: str


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
    def __init__(self, client: TestClient, csrf: str) -> None:
        self.client = client
        self.csrf = csrf

    def get(self, *args: object, **kwargs: object) -> Any:
        return self.client.get(*args, **kwargs)

    def post(self, *args: object, **kwargs: object) -> Any:
        return self.client.post(*args, **kwargs)


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
