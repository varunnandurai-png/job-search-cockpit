from base64 import urlsafe_b64encode
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from secrets import token_urlsafe
from subprocess import TimeoutExpired, run
from threading import RLock
from time import monotonic
from typing import Protocol
from urllib.parse import urlencode, urlsplit

import httpx

_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_DRIVE_FILE_SCOPE = "https://www.googleapis.com/auth/drive.file"
_STATE_TTL_SECONDS = 300.0
_KEYCHAIN_SERVICE = "com.job-search-cockpit.google-drive"
_KEYCHAIN_ACCOUNT = "drive.file"


class DriveAuthorizationError(ValueError):
    """Raised when a private Drive authorization request is invalid or unavailable."""


@dataclass(frozen=True, slots=True)
class DriveAuthorizationRequest:
    operation_id: str
    state: str
    authorization_url: str


@dataclass(frozen=True, slots=True)
class _PendingAuthorization:
    operation_id: str
    session_id: str
    redirect_uri: str
    code_verifier: str
    expires_at: float


class DriveCredentialStore(Protocol):
    def store_refresh_token(self, refresh_token: str) -> None: ...

    def load_refresh_token(self) -> str | None: ...

    def delete_refresh_token(self) -> None: ...


class DriveAuthorizationService:
    """Creates one-use, session-bound Google OAuth requests without contacting Google."""

    def __init__(
        self,
        *,
        client_id: str,
        http_client: httpx.Client | None = None,
        credential_store: DriveCredentialStore | None = None,
    ) -> None:
        if not client_id.strip() or len(client_id) > 240:
            raise ValueError("The Google desktop client ID is invalid.")
        self._client_id = client_id
        self._http_client = http_client or httpx.Client(
            follow_redirects=False, timeout=httpx.Timeout(30.0, connect=10.0)
        )
        self._credential_store = credential_store or MacOSKeychainCredentialStore()
        self._pending: dict[str, _PendingAuthorization] = {}
        self._lock = RLock()

    def begin(
        self, operation_id: str, session_id: str, redirect_uri: str
    ) -> DriveAuthorizationRequest:
        self._validate_bounded_id(operation_id, "operation")
        self._validate_bounded_id(session_id, "session")
        self._validate_loopback_uri(redirect_uri)
        verifier = token_urlsafe(64)
        challenge = urlsafe_b64encode(sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        state = token_urlsafe(32)
        pending = _PendingAuthorization(
            operation_id=operation_id,
            session_id=session_id,
            redirect_uri=redirect_uri,
            code_verifier=verifier,
            expires_at=monotonic() + _STATE_TTL_SECONDS,
        )
        with self._lock:
            self._pending[state] = pending
        query = urlencode(
            {
                "client_id": self._client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": _DRIVE_FILE_SCOPE,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": state,
                "access_type": "offline",
                "prompt": "consent",
            }
        )
        return DriveAuthorizationRequest(
            operation_id=operation_id,
            state=state,
            authorization_url=f"{_AUTHORIZATION_ENDPOINT}?{query}",
        )

    def deny(self, state: str, reason_code: str, session_id: str) -> str:
        if reason_code != "access_denied":
            raise DriveAuthorizationError("The Google authorization response is invalid.")
        return self._consume(state, session_id).operation_id

    def complete(
        self, state: str, code: str, session_id: str, before_request: Callable[[], None]
    ) -> str:
        if not 1 <= len(code) <= 4096:
            raise DriveAuthorizationError("The Google authorization response is invalid.")
        pending = self._consume(state, session_id)
        before_request()
        try:
            response = self._http_client.post(
                _TOKEN_ENDPOINT,
                data={
                    "client_id": self._client_id,
                    "code": code,
                    "code_verifier": pending.code_verifier,
                    "redirect_uri": pending.redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
        except httpx.HTTPError as error:
            raise DriveAuthorizationError(
                "Google authorization is temporarily unavailable."
            ) from error
        if response.status_code != 200:
            raise DriveAuthorizationError("Google authorization was not accepted.")
        try:
            payload = response.json()
        except ValueError as error:
            raise DriveAuthorizationError(
                "The Google authorization response is invalid."
            ) from error
        if not isinstance(payload, dict):
            raise DriveAuthorizationError("The Google authorization response is invalid.")
        access_token = payload.get("access_token")
        refresh_token = payload.get("refresh_token")
        scope = payload.get("scope")
        token_type = payload.get("token_type")
        if (
            not isinstance(access_token, str)
            or not 1 <= len(access_token) <= 4096
            or not isinstance(refresh_token, str)
            or scope != _DRIVE_FILE_SCOPE
            or token_type != "Bearer"
        ):
            raise DriveAuthorizationError("The Google authorization response is invalid.")
        self._credential_store.store_refresh_token(refresh_token)
        return access_token

    def access_token(self, before_request: Callable[[], None]) -> str | None:
        refresh_token = self._credential_store.load_refresh_token()
        if refresh_token is None:
            return None
        before_request()
        try:
            response = self._http_client.post(
                _TOKEN_ENDPOINT,
                data={
                    "client_id": self._client_id,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
        except httpx.HTTPError as error:
            raise DriveAuthorizationError(
                "Google authorization is temporarily unavailable."
            ) from error
        if response.status_code != 200:
            if _is_invalid_grant(response):
                self._credential_store.delete_refresh_token()
                raise DriveAuthorizationError("Google permission expired.")
            raise DriveAuthorizationError("Google authorization was not accepted.")
        try:
            payload = response.json()
        except ValueError as error:
            raise DriveAuthorizationError(
                "The Google authorization response is invalid."
            ) from error
        access_token = payload.get("access_token") if isinstance(payload, dict) else None
        returned_scope = payload.get("scope") if isinstance(payload, dict) else None
        if (
            not isinstance(access_token, str)
            or not 1 <= len(access_token) <= 4096
            or (returned_scope is not None and returned_scope != _DRIVE_FILE_SCOPE)
        ):
            raise DriveAuthorizationError("The Google authorization response is invalid.")
        return access_token

    def _consume(self, state: str, session_id: str) -> _PendingAuthorization:
        self._validate_bounded_id(state, "authorization state")
        self._validate_bounded_id(session_id, "session")
        with self._lock:
            pending = self._pending.pop(state, None)
        if pending is None or pending.expires_at < monotonic() or pending.session_id != session_id:
            raise DriveAuthorizationError("The Google authorization request is unavailable.")
        return pending

    @staticmethod
    def _validate_bounded_id(value: str, label: str) -> None:
        if not 1 <= len(value.strip()) <= 120:
            raise DriveAuthorizationError(f"The {label} ID is invalid.")

    @staticmethod
    def _validate_loopback_uri(redirect_uri: str) -> None:
        parsed = urlsplit(redirect_uri)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or parsed.port is None
            or parsed.path != "/phase-2/drive-backups/oauth/callback"
            or parsed.query
            or parsed.fragment
        ):
            raise DriveAuthorizationError("The Google authorization callback address is invalid.")


def _is_invalid_grant(response: httpx.Response) -> bool:
    try:
        payload = response.json()
    except ValueError:
        return False
    return isinstance(payload, dict) and payload.get("error") == "invalid_grant"


class MacOSKeychainCredentialStore:
    """Stores a refresh token only in the current user's macOS Keychain."""

    def __init__(self, runner: Callable[[tuple[str, ...], str], None] | None = None) -> None:
        self._runner = runner or self._run

    def store_refresh_token(self, refresh_token: str) -> None:
        if not 1 <= len(refresh_token) <= 4096:
            raise DriveAuthorizationError("The Google authorization response is invalid.")
        self._runner(
            (
                "/usr/bin/security",
                "add-generic-password",
                "-U",
                "-s",
                _KEYCHAIN_SERVICE,
                "-a",
                _KEYCHAIN_ACCOUNT,
                "-w",
            ),
            f"{refresh_token}\n",
        )

    def delete_refresh_token(self) -> None:
        self._runner(
            (
                "/usr/bin/security",
                "delete-generic-password",
                "-s",
                _KEYCHAIN_SERVICE,
                "-a",
                _KEYCHAIN_ACCOUNT,
            ),
            "",
        )

    @staticmethod
    def load_refresh_token() -> str | None:
        try:
            result = run(
                (
                    "/usr/bin/security",
                    "find-generic-password",
                    "-s",
                    _KEYCHAIN_SERVICE,
                    "-a",
                    _KEYCHAIN_ACCOUNT,
                    "-w",
                ),
                timeout=5,
                capture_output=True,
                text=True,
                check=False,
            )
        except (OSError, TimeoutExpired) as error:
            raise DriveAuthorizationError("The macOS Keychain is unavailable.") from error
        if result.returncode != 0:
            return None
        token = result.stdout.rstrip("\n")
        if not token:
            return None
        if len(token) > 4096:
            raise DriveAuthorizationError("The macOS Keychain is unavailable.")
        return token

    @staticmethod
    def _run(args: tuple[str, ...], value: str) -> None:
        try:
            result = run(args, input=value, timeout=5, capture_output=True, text=True, check=False)
        except (OSError, TimeoutExpired) as error:
            raise DriveAuthorizationError("The macOS Keychain is unavailable.") from error
        if result.returncode != 0:
            raise DriveAuthorizationError("The macOS Keychain is unavailable.")
