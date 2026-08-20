import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel, create_engine


@pytest.fixture
def sqlite_engine() -> Engine:
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    SQLModel.metadata.create_all(engine)
    return engine
