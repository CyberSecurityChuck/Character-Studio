from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import URL, Engine, create_engine, event, text
from sqlalchemy.orm import Session

from backend.configuration import Settings, asset_path, initialize_storage

SCHEMA_REVISION = "0009_quality"


def open_database(settings: Settings) -> Engine:
    initialize_storage(settings)
    engine = create_engine(
        URL.create("sqlite", database=str(asset_path(settings, "studio.db"))),
        connect_args={"check_same_thread": False, "timeout": 5},
    )

    @event.listens_for(engine, "connect")
    def configure_sqlite(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=FULL")
        cursor.close()

    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    try:
        with engine.connect() as connection:
            # SQLite changes a CHECK constraint by rebuilding the table, which its documented
            # procedure does with foreign keys off; every reference is verified before commit.
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
            try:
                with connection.begin():
                    config.attributes["connection"] = connection
                    command.upgrade(config, "head")
                    if connection.exec_driver_sql("PRAGMA foreign_key_check").first():
                        raise RuntimeError("The database upgrade would break saved references.")
            finally:
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                connection.commit()
    except Exception:
        engine.dispose()
        raise
    return engine


@contextmanager
def writing_session(engine: Engine):
    # Serialize local writes before reading revisions or touching files.
    with Session(engine) as session:
        session.execute(text("BEGIN IMMEDIATE"))
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise
