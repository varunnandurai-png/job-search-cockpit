from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from job_search_cockpit.config import Settings
from job_search_cockpit.search_profile.catalog import build_profile_v1
from job_search_cockpit.search_profile.service import (
    ProfileConfirmationError,
    ProfileVersionConflict,
    confirm_profile_change,
    get_active_profile,
    profile_diff_digest,
    seed_profile_v1,
)
from job_search_cockpit.storage.database import (
    create_engine_for,
    session_factory_for,
    upgrade_database,
)
from job_search_cockpit.storage.models import SearchProfileVersion
from job_search_cockpit.storage.mutation import AppInstanceLock, MutationCoordinator


@contextmanager
def _coordinator(tmp_path: Path) -> Iterator[MutationCoordinator]:
    settings = Settings.for_tests(tmp_path / "data", tmp_path / "sources")
    upgrade_database(f"sqlite:///{settings.database_path}")
    engine = create_engine_for(settings)
    lock = AppInstanceLock.acquire(settings)
    coordinator = MutationCoordinator(settings, engine, lock)
    try:
        yield coordinator
    finally:
        coordinator.dispose()
        lock.release()


def test_profile_change_requires_exact_confirmation(tmp_path: Path) -> None:
    with _coordinator(tmp_path) as coordinator:
        seed_profile_v1(coordinator)
        changed = build_profile_v1().model_copy(update={"notice_period_days": 30})
        with pytest.raises(ProfileConfirmationError):
            confirm_profile_change(
                coordinator,
                changed,
                "role update",
                "yes",
                expected_active_version=1,
                expected_diff_digest=profile_diff_digest(build_profile_v1(), changed),
            )
        factory = session_factory_for(coordinator.engine)
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(SearchProfileVersion)) == 1


def test_confirmed_profile_change_creates_new_active_version(tmp_path: Path) -> None:
    with _coordinator(tmp_path) as coordinator:
        seed_profile_v1(coordinator)
        changed = build_profile_v1().model_copy(update={"notice_period_days": 30})
        created = confirm_profile_change(
            coordinator,
            changed,
            "Confirmed notice-period change",
            "CREATE NEW SEARCH PROFILE VERSION",
            expected_active_version=1,
            expected_diff_digest=profile_diff_digest(build_profile_v1(), changed),
        )
        assert created.version_number == 2
        assert created.active is True
        factory = session_factory_for(coordinator.engine)
        with factory() as session:
            assert get_active_profile(session).version_number == 2


def test_profile_history_payload_cannot_be_rewritten(tmp_path: Path) -> None:
    with _coordinator(tmp_path) as coordinator:
        seeded = seed_profile_v1(coordinator)
        factory = session_factory_for(coordinator.engine)
        with (
            pytest.raises(IntegrityError, match="history is immutable"),
            factory.begin() as session,
        ):
            stored = session.get(SearchProfileVersion, seeded.id)
            assert stored is not None
            stored.reason = "Rewritten history"


def test_stale_profile_change_is_rejected(tmp_path: Path) -> None:
    with _coordinator(tmp_path) as coordinator:
        seed_profile_v1(coordinator)
        changed = build_profile_v1().model_copy(update={"notice_period_days": 30})
        digest = profile_diff_digest(build_profile_v1(), changed)
        confirm_profile_change(
            coordinator,
            changed,
            "Confirmed notice-period change",
            "CREATE NEW SEARCH PROFILE VERSION",
            expected_active_version=1,
            expected_diff_digest=digest,
        )
        with pytest.raises(ProfileVersionConflict):
            confirm_profile_change(
                coordinator,
                changed,
                "Repeated stale form",
                "CREATE NEW SEARCH PROFILE VERSION",
                expected_active_version=1,
                expected_diff_digest=digest,
            )
