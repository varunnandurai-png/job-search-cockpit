import sqlite3

import pytest
from sqlalchemy import func, select

from job_search_cockpit.launcher import StartupError, prepare_vault
from job_search_cockpit.storage.database import session_factory_for
from job_search_cockpit.storage.models import SearchProfileVersion
from job_search_cockpit.storage.mutation import VaultAlreadyOpen


def _close(prepared) -> None:
    prepared.coordinator.dispose()
    prepared.instance_lock.release()


def test_fresh_and_existing_vault_seed_profile_once(vault_settings, monkeypatch):
    monkeypatch.setattr("job_search_cockpit.launcher.sys.platform", "darwin")
    first = prepare_vault(vault_settings)
    _close(first)
    second = prepare_vault(vault_settings)
    try:
        with session_factory_for(second.engine)() as session:
            assert session.scalar(select(func.count()).select_from(SearchProfileVersion)) == 1
    finally:
        _close(second)


def test_non_macos_refuses_before_creating_private_directory(vault_settings, monkeypatch):
    monkeypatch.setattr("job_search_cockpit.launcher.sys.platform", "linux")
    with pytest.raises(StartupError, match="macOS"):
        prepare_vault(vault_settings)
    assert not vault_settings.data_dir.exists()


def test_corrupt_existing_database_is_not_replaced(vault_settings, monkeypatch):
    monkeypatch.setattr("job_search_cockpit.launcher.sys.platform", "darwin")
    vault_settings.data_dir.mkdir(parents=True)
    original = b"not a sqlite database"
    vault_settings.database_path.write_bytes(original)
    with pytest.raises(StartupError, match="integrity"):
        prepare_vault(vault_settings)
    assert vault_settings.database_path.read_bytes() == original


def test_second_prepared_instance_is_refused(vault_settings, monkeypatch):
    monkeypatch.setattr("job_search_cockpit.launcher.sys.platform", "darwin")
    prepared = prepare_vault(vault_settings)
    try:
        with pytest.raises(VaultAlreadyOpen):
            prepare_vault(vault_settings)
    finally:
        _close(prepared)


def test_corrupt_recovery_ledger_refuses_startup(vault_settings, monkeypatch):
    monkeypatch.setattr("job_search_cockpit.launcher.sys.platform", "darwin")
    prepared = prepare_vault(vault_settings)
    _close(prepared)
    ledger = vault_settings.data_dir / "recovery.jsonl"
    ledger.write_text('{"altered":true}\n', encoding="utf-8")
    with pytest.raises(StartupError, match="recovery history"):
        prepare_vault(vault_settings)


def test_fresh_vault_has_sqlite_integrity_and_owner_only_files(vault_settings, monkeypatch):
    monkeypatch.setattr("job_search_cockpit.launcher.sys.platform", "darwin")
    prepared = prepare_vault(vault_settings)
    try:
        with sqlite3.connect(vault_settings.database_path) as connection:
            assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert vault_settings.data_dir.stat().st_mode & 0o777 == 0o700
        assert vault_settings.database_path.stat().st_mode & 0o777 == 0o600
    finally:
        _close(prepared)
