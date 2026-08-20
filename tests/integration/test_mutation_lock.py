from pathlib import Path

import pytest

from job_search_cockpit.config import Settings
from job_search_cockpit.storage.mutation import AppInstanceLock, VaultAlreadyOpen


def test_second_process_cannot_open_same_vault(tmp_path: Path) -> None:
    settings = Settings.for_tests(tmp_path / "data", tmp_path / "sources")
    first = AppInstanceLock.acquire(settings)
    try:
        with pytest.raises(VaultAlreadyOpen):
            AppInstanceLock.acquire(settings)
    finally:
        first.release()


def test_released_instance_lock_can_be_acquired_again(tmp_path: Path) -> None:
    settings = Settings.for_tests(tmp_path / "data", tmp_path / "sources")
    first = AppInstanceLock.acquire(settings)
    first.release()
    second = AppInstanceLock.acquire(settings)
    second.release()
