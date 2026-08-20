from collections.abc import Iterator
from contextlib import contextmanager

from job_search_cockpit.config import Settings
from job_search_cockpit.imports.service import ImportService
from job_search_cockpit.readiness.service import ReadinessService
from job_search_cockpit.search_profile.service import seed_profile_v1
from job_search_cockpit.storage.database import create_engine_for, upgrade_database
from job_search_cockpit.storage.mutation import AppInstanceLock, MutationCoordinator
from tests.support.builders import FixedClock


@contextmanager
def _vault(settings: Settings) -> Iterator[tuple[MutationCoordinator, FixedClock]]:
    upgrade_database(f"sqlite:///{settings.database_path}")
    engine = create_engine_for(settings)
    lock = AppInstanceLock.acquire(settings)
    coordinator = MutationCoordinator(settings, engine, lock)
    clock = FixedClock()
    try:
        yield coordinator, clock
    finally:
        coordinator.dispose()
        lock.release()


def test_readiness_uses_latest_complete_run_and_reports_review_counts(
    vault_settings: Settings,
) -> None:
    with _vault(vault_settings) as (coordinator, clock):
        seed_profile_v1(coordinator)
        importer = ImportService(vault_settings, coordinator, monotonic_clock=clock.monotonic_now)
        importer.apply(importer.preview("session-1", clock.now()).id, "session-1", clock.now())
        report = ReadinessService(coordinator).report()
        assert report.ready_for_phase_2 is False
        assert report.unresolved > 0
        assert report.open_conflicts >= 2
        assert report.latest_import_complete is True
        assert report.active_profile_version == 1
