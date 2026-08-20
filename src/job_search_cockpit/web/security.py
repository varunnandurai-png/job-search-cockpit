import hmac
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol


class WallClock(Protocol):
    def now(self) -> datetime: ...


class MonotonicClock(Protocol):
    def now(self) -> float: ...


@dataclass(slots=True)
class LaunchSession:
    token: str
    cookie_secret: str
    csrf_secret: str
    issued_at: datetime
    monotonic_deadline: float
    consumed: bool

    @classmethod
    def fresh(
        cls,
        wall_clock: WallClock | None = None,
        monotonic_clock: MonotonicClock | None = None,
    ) -> "LaunchSession":
        issued_at = wall_clock.now() if wall_clock else datetime.now(UTC)
        monotonic_now = monotonic_clock.now() if monotonic_clock else time.monotonic()
        return cls(
            token=secrets.token_urlsafe(32),
            cookie_secret=secrets.token_urlsafe(32),
            csrf_secret=secrets.token_urlsafe(32),
            issued_at=issued_at,
            monotonic_deadline=monotonic_now + 300.0,
            consumed=False,
        )

    @property
    def session_id(self) -> str:
        return sha256(self.cookie_secret.encode()).hexdigest()

    @staticmethod
    def _signed(payload: str, secret: str) -> str:
        signature = hmac.new(secret.encode(), payload.encode(), sha256).hexdigest()
        return f"{payload}.{signature}"

    @property
    def session_cookie(self) -> str:
        return self._signed(self.session_id, self.cookie_secret)

    @property
    def csrf_token(self) -> str:
        return self._signed(self.session_id, self.csrf_secret)

    def exchange(self, candidate: str, monotonic_now: float | None = None) -> bool:
        now = time.monotonic() if monotonic_now is None else monotonic_now
        valid = (
            not self.consumed
            and now < self.monotonic_deadline
            and secrets.compare_digest(candidate, self.token)
        )
        if valid:
            self.consumed = True
        return valid

    def valid_cookie(self, value: str | None) -> bool:
        return value is not None and secrets.compare_digest(value, self.session_cookie)

    def valid_csrf(self, value: str | None) -> bool:
        return value is not None and secrets.compare_digest(value, self.csrf_token)
