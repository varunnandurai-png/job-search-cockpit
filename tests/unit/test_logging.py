import logging
from pathlib import Path

from job_search_cockpit.config import Settings
from job_search_cockpit.logging import configure_logging, redact_sensitive


def test_log_redaction_removes_sensitive_values() -> None:
    message = redact_sensitive("email=person@example.com phone=+91 99999 99999 token=secret")
    assert "person@example.com" not in message
    assert "99999" not in message
    assert "secret" not in message


def test_configured_log_redacts_structured_claim_values(tmp_path: Path) -> None:
    settings = Settings.for_tests(tmp_path / "data", tmp_path / "sources")
    configure_logging(settings)
    logger = logging.getLogger("job_search_cockpit.import")
    logger.info("import_failed claim_value=%s", "Private career claim")
    for handler in logging.getLogger("job_search_cockpit").handlers:
        handler.flush()

    log_path = settings.data_dir / "logs" / "cockpit.log"
    text = log_path.read_text(encoding="utf-8")
    assert "import_failed" in text
    assert "Private career claim" not in text
    assert log_path.stat().st_mode & 0o777 == 0o600
    assert log_path.parent.stat().st_mode & 0o777 == 0o700
