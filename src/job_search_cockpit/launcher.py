import logging
import socket
import sqlite3
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from job_search_cockpit.config import Settings
from job_search_cockpit.facts.permissions import NamedUseService, PermissionService
from job_search_cockpit.facts.review import ReviewService
from job_search_cockpit.imports.service import ImportService
from job_search_cockpit.logging import configure_logging
from job_search_cockpit.ports import PreparedVault, ServiceBundle
from job_search_cockpit.readiness.service import ReadinessService
from job_search_cockpit.search_profile.service import seed_profile_v1
from job_search_cockpit.storage.backup import copy_database_online
from job_search_cockpit.storage.database import create_engine_for, upgrade_database
from job_search_cockpit.storage.mutation import AppInstanceLock, MutationCoordinator
from job_search_cockpit.storage.recovery_ledger import InvalidRecoveryLedger
from job_search_cockpit.web.app import create_app
from job_search_cockpit.web.security import LaunchSession

CURRENT_SCHEMA = "0001_phase_1_vault"


class StartupError(RuntimeError):
    """A startup failure with a safe, plain-language recovery action."""


def _sqlite_state(path: Path) -> tuple[str, str | None]:
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            version_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='alembic_version'"
            ).fetchone()
            version = (
                connection.execute("SELECT version_num FROM alembic_version").fetchone()
                if version_table
                else None
            )
    except sqlite3.Error as error:
        raise StartupError(
            "The vault failed its integrity check. Keep the file unchanged and restore a "
            "verified safety copy."
        ) from error
    if integrity is None or integrity[0] != "ok":
        raise StartupError(
            "The vault failed its integrity check. Keep the file unchanged and restore a "
            "verified safety copy."
        )
    return str(integrity[0]), str(version[0]) if version else None


def _upgrade_existing(
    settings: Settings,
    coordinator: MutationCoordinator,
    current_version: str | None,
) -> None:
    if current_version is None:
        raise StartupError(
            "The existing vault has no recognized schema version. Keep it unchanged and use "
            "Restore help before starting."
        )
    prepared = settings.data_dir / ".upgrade-prepared.sqlite3"
    prepared.unlink(missing_ok=True)
    copy_database_online(settings.database_path, prepared)
    try:
        upgrade_database(f"sqlite:///{prepared}")
        _integrity, upgraded_version = _sqlite_state(prepared)
        if upgraded_version != CURRENT_SCHEMA:
            raise StartupError("The migrated copy did not reach the expected schema.")
        coordinator.install_prepared_database(prepared, "before_schema_upgrade")
    except Exception as error:
        prepared.unlink(missing_ok=True)
        if isinstance(error, StartupError):
            raise
        raise StartupError(
            "The vault upgrade failed. The original vault remains available; use Restore help."
        ) from error


def prepare_vault(settings: Settings) -> PreparedVault:
    if sys.platform != "darwin":
        raise StartupError("Job Search Cockpit Phase 1 requires macOS.")
    settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    settings.data_dir.chmod(0o700)
    settings.backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    settings.backup_dir.chmod(0o700)
    configure_logging(settings)
    logger = logging.getLogger("job_search_cockpit.launcher")
    instance_lock = AppInstanceLock.acquire(settings)
    coordinator: MutationCoordinator | None = None
    try:
        fresh = not settings.database_path.exists() or settings.database_path.stat().st_size == 0
        if fresh:
            upgrade_database(f"sqlite:///{settings.database_path}")
            settings.database_path.chmod(0o600)
            _integrity, version = _sqlite_state(settings.database_path)
            if version != CURRENT_SCHEMA:
                raise StartupError("The new vault schema could not be verified.")
            engine = create_engine_for(settings)
            coordinator = MutationCoordinator(settings, engine, instance_lock)
        else:
            _integrity, version = _sqlite_state(settings.database_path)
            engine = create_engine_for(settings)
            coordinator = MutationCoordinator(settings, engine, instance_lock)
            if version != CURRENT_SCHEMA:
                _upgrade_existing(settings, coordinator, version)

        try:
            ledger_entries = coordinator.recovery_ledger.read_all()
        except InvalidRecoveryLedger as error:
            raise StartupError(
                "The recovery history is damaged. Keep it unchanged and use Restore help."
            ) from error
        seed_profile_v1(coordinator)
        coordinator.reconcile_import_attempt_events(ledger_entries)
        permissions = PermissionService(coordinator)
        permissions.expire_due(datetime.now(UTC))
        _integrity, final_version = _sqlite_state(settings.database_path)
        if final_version != CURRENT_SCHEMA:
            raise StartupError("The prepared vault schema could not be verified.")
        services = ServiceBundle(
            import_service=ImportService(settings, coordinator),
            review_service=ReviewService(coordinator),
            readiness_service=ReadinessService(coordinator),
            permission_service=permissions,
            named_use_service=NamedUseService(coordinator),
        )
        return PreparedVault(instance_lock, coordinator, coordinator.engine, services)
    except Exception:
        logger.exception("vault_preparation_failed")
        if coordinator is not None:
            coordinator.dispose()
        instance_lock.release()
        raise


@dataclass(slots=True)
class LaunchPlan:
    socket: socket.socket
    port: int
    url: str
    launch_session: LaunchSession
    prepared: PreparedVault
    app: FastAPI
    _closed: bool = field(default=False, init=False)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.socket.close()
        coordinator = self.prepared.coordinator
        if isinstance(coordinator, MutationCoordinator):
            coordinator.dispose()
        self.prepared.instance_lock.release()


def build_launch_plan(settings: Settings) -> LaunchPlan:
    prepared = prepare_vault(settings)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        port = int(listener.getsockname()[1])
        launch_session = LaunchSession.fresh()
        app = create_app(settings, prepared, launch_session, port)
        url = f"http://127.0.0.1:{port}/launch?token={launch_session.token}"
        return LaunchPlan(listener, port, url, launch_session, prepared, app)
    except Exception:
        logging.getLogger("job_search_cockpit.launcher").exception("launch_plan_failed")
        listener.close()
        coordinator = prepared.coordinator
        if isinstance(coordinator, MutationCoordinator):
            coordinator.dispose()
        prepared.instance_lock.release()
        raise


def main() -> int:
    try:
        plan = build_launch_plan(Settings())
    except Exception as error:
        print(f"The cockpit could not start: {error}")
        return 1
    server = uvicorn.Server(
        uvicorn.Config(plan.app, host="127.0.0.1", port=plan.port, log_level="warning")
    )
    thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [plan.socket]},
        daemon=True,
    )
    try:
        thread.start()
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.02)
        if not server.started:
            raise StartupError("The private local web server did not start.")
        webbrowser.open(plan.url)
        print("Job Search Cockpit is open in your browser. Press Control-C here to stop it.")
        thread.join()
        return 0
    except KeyboardInterrupt:
        print("Stopping Job Search Cockpit safely.")
        server.should_exit = True
        thread.join(timeout=10)
        if thread.is_alive():
            server.force_exit = True
            thread.join(timeout=10)
        if thread.is_alive():
            print("The local server did not stop; the vault lock will remain held until exit.")
            return 1
        return 0
    except Exception as error:
        logging.getLogger("job_search_cockpit.launcher").exception("server_start_failed")
        print(f"The cockpit stopped before opening: {error}")
        server.should_exit = True
        thread.join(timeout=10)
        return 1
    finally:
        if not thread.is_alive():
            plan.close()


if __name__ == "__main__":
    raise SystemExit(main())
