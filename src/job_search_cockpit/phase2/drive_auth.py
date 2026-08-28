from base64 import urlsafe_b64encode
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from secrets import token_urlsafe
from subprocess import run
from threading import RLock
from time import monotonic
from urllib.parse import urlencode, urlsplit

_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
_DRIVE_FILE_SCOPE = "https://www.googleapis.com/auth/drive.file"
_STATE_TTL_SECONDS = 300.0
_KEYCHAIN_SERVICE = "job-search-cockpit.private-drive-backup"
_KEYCHAIN_ACCOUNT = "refresh-token"


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


class DriveAuthorizationService:
    """Creates one-use, session-bound Google OAuth requests without contacting Google."""

    def __init__(self, *, client_id: str) -> None:
        if not client_id.strip() or len(client_id) > 240:
            raise ValueError("The Google desktop client ID is invalid.")
        self._client_id = client_id
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

    @staticmethod
    def _run(args: tuple[str, ...], value: str) -> None:
        try:
            result = run(args, input=value, timeout=5, capture_output=True, text=True, check=False)
        except OSError as error:
            raise DriveAuthorizationError("The macOS Keychain is unavailable.") from error
        if result.returncode != 0:
            raise DriveAuthorizationError("The macOS Keychain is unavailable.")
