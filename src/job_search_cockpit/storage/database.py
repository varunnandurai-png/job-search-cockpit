import sqlite3
from pathlib import Path
from typing import Any

from alembic.config import Config
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from job_search_cockpit.config import Settings


def _set_sqlite_pragmas(dbapi_connection: sqlite3.Connection, _record: Any) -> None:
    previous_autocommit = dbapi_connection.autocommit
    dbapi_connection.autocommit = True
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=FULL")
    finally:
        cursor.close()
        dbapi_connection.autocommit = previous_autocommit


def create_engine_for(settings: Settings) -> Engine:
    settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    settings.data_dir.chmod(0o700)
    engine = create_engine(
        f"sqlite:///{settings.database_path}",
        connect_args={"autocommit": False, "check_same_thread": False},
    )
    event.listen(engine, "connect", _set_sqlite_pragmas)
    return engine


def session_factory_for(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def upgrade_database(database_url: str) -> None:
    project_root = Path(__file__).resolve().parents[3]
    configuration = Config(project_root / "alembic.ini")
    configuration.set_main_option("script_location", str(project_root / "alembic"))
    configuration.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(configuration, "head")
