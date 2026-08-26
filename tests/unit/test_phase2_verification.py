from datetime import UTC, datetime

from job_search_cockpit.phase2.verification import _as_utc


def test_verification_expiry_normalizes_sqlite_naive_datetimes_to_utc() -> None:
    normalized = _as_utc(datetime(2026, 8, 26, 12, 0))

    assert normalized == datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
