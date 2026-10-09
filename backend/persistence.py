from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import URL, Engine, create_engine, event

from backend.configuration import Settings, asset_path, initialize_storage

SCHEMA_REVISION = "0001_foundation"


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
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    except Exception:
        engine.dispose()
        raise
    return engine
