from urllib.parse import parse_qs, urlsplit

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


def test_callback_state_is_one_use_short_lived_and_session_bound() -> None:
    service = DriveAuthorizationService(client_id="desktop-client-id")
    started = service.begin("operation-1", "session-1", LOOPBACK_URI)

    operation_id = service.deny(started.state, "access_denied", "session-1")

    assert operation_id == "operation-1"
    with pytest.raises(DriveAuthorizationError, match="unavailable"):
        service.deny(started.state, "access_denied", "session-1")
