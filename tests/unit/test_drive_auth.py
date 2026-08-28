from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from job_search_cockpit.phase2.drive_auth import (
    DriveAuthorizationError,
    DriveAuthorizationService,
    MacOSKeychainCredentialStore,
)

LOOPBACK_URI = "http://127.0.0.1:8765/phase-2/drive-backups/oauth/callback"


def test_begin_uses_exact_scope_s256_state_and_loopback() -> None:
    service = DriveAuthorizationService(client_id="desktop-client-id")

    request = service.begin(
        operation_id="operation-1",
        session_id="launch-session-1",
        redirect_uri=LOOPBACK_URI,
    )

    query = parse_qs(urlsplit(request.authorization_url).query)
    assert urlsplit(request.authorization_url)._replace(query="").geturl() == (
        "https://accounts.google.com/o/oauth2/v2/auth"
    )
    assert query["scope"] == ["https://www.googleapis.com/auth/drive.file"]
    assert query["response_type"] == ["code"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["redirect_uri"] == [LOOPBACK_URI]
    assert len(query["state"][0]) >= 43


def test_keychain_write_passes_refresh_token_on_stdin_not_argv() -> None:
    calls: list[tuple[tuple[str, ...], str]] = []

    def runner(args: tuple[str, ...], value: str) -> None:
        calls.append((args, value))

    store = MacOSKeychainCredentialStore(runner)

    store.store_refresh_token("refresh-secret")

    command, supplied_input = calls[0]
    assert "refresh-secret" not in command
    assert supplied_input == "refresh-secret\n"
    assert command[-1] == "-w"
    assert "com.job-search-cockpit.google-drive" in command
    assert "drive.file" in command


def test_callback_state_is_one_use_short_lived_and_session_bound() -> None:
    service = DriveAuthorizationService(client_id="desktop-client-id")
    started = service.begin("operation-1", "session-1", LOOPBACK_URI)

    operation_id = service.deny(started.state, "access_denied", "session-1")

    assert operation_id == "operation-1"
    with pytest.raises(DriveAuthorizationError, match="unavailable"):
        service.deny(started.state, "access_denied", "session-1")


def test_complete_exchanges_one_use_code_and_stores_only_refresh_permission() -> None:
    stored: list[str] = []
    revalidations: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://oauth2.googleapis.com/token"
        assert request.headers["content-type"].startswith("application/x-www-form-urlencoded")
        return httpx.Response(
            200,
            json={
                "access_token": "short-lived-access",
                "refresh_token": "stored-in-keychain",
                "scope": "https://www.googleapis.com/auth/drive.file",
                "token_type": "Bearer",
            },
        )

    service = DriveAuthorizationService(
        client_id="desktop-client-id",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        credential_store=MacOSKeychainCredentialStore(
            lambda _args, value: stored.append(value)
        ),
    )
    started = service.begin("operation-1", "session-1", LOOPBACK_URI)

    token = service.complete(
        started.state,
        "code-1",
        "session-1",
        lambda: revalidations.append("ok"),
    )

    assert token == "short-lived-access"
    assert stored == ["stored-in-keychain\n"]
    assert revalidations == ["ok"]


def test_access_token_returns_none_when_no_keychain_permission_exists() -> None:
    class EmptyCredentialStore:
        def store_refresh_token(self, refresh_token: str) -> None:
            raise AssertionError(refresh_token)

        def load_refresh_token(self) -> str | None:
            return None

    service = DriveAuthorizationService(
        client_id="desktop-client-id",
        credential_store=EmptyCredentialStore(),
    )

    assert service.access_token(lambda: None) is None
