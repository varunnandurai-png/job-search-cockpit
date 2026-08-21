import logging
import os
import re
from collections.abc import Iterable
from pathlib import Path
from types import TracebackType

from job_search_cockpit.config import Settings

_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)")
_CLAIM_VALUE = re.compile(r"(?i)\bclaim(?:_value)?\s*=\s*.*$")
_SECRET = re.compile(r"(?i)\b(token|csrf|cookie|password|secret|claim(?:_value)?)\s*=\s*([^\s,;]+)")
_SENSITIVE_FIELD_PARTS = ("token", "csrf", "cookie", "password", "secret", "claim_value")


def redact_sensitive(message: object, sensitive_values: Iterable[object] = ()) -> str:
    redacted = str(message)
    redacted = _EMAIL.sub("[REDACTED]", redacted)
    redacted = _PHONE.sub("[REDACTED]", redacted)
    redacted = _CLAIM_VALUE.sub("claim_value=[REDACTED]", redacted)
    redacted = _SECRET.sub(lambda match: f"{match.group(1)}=[REDACTED]", redacted)
    for value in sensitive_values:
        rendered = str(value)
        if rendered:
            redacted = redacted.replace(rendered, "[REDACTED]")
    return redacted


class _RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        sensitive_values = [
            value
            for key, value in vars(record).items()
            if any(part in key.lower() for part in _SENSITIVE_FIELD_PARTS)
        ]
        rendered = record.getMessage()
        record.msg = redact_sensitive(rendered, sensitive_values)
        record.args = ()
        return True


class _SafeFormatter(logging.Formatter):
    def formatException(
        self,
        exc_info: (
            tuple[type[BaseException], BaseException, TracebackType | None]
            | tuple[None, None, None]
        ),
    ) -> str:
        exception_type = exc_info[0]
        return exception_type.__name__ if exception_type is not None else "Exception"


def _protected_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


def configure_logging(settings: Settings) -> None:
    _protected_directory(settings.data_dir)
    log_dir = settings.data_dir / "logs"
    _protected_directory(log_dir)
    log_path = log_dir / "cockpit.log"
    descriptor = os.open(log_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    os.close(descriptor)
    log_path.chmod(0o600)

    logger = logging.getLogger("job_search_cockpit")
    logger.disabled = False
    logger.setLevel(logging.INFO)
    for name, candidate in logging.Logger.manager.loggerDict.items():
        if name.startswith("job_search_cockpit.") and isinstance(candidate, logging.Logger):
            candidate.disabled = False
    for handler in tuple(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.addFilter(_RedactingFilter())
    handler.setFormatter(_SafeFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
