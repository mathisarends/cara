from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.exc import OperationalError

from gateway.app import create_app
from gateway.features.health.infrastructure import DatabaseReadinessCheck
from gateway.infrastructure import DatabaseSettings


def _create_test_app():
    return create_app(
        DatabaseSettings(database_url=SecretStr("sqlite+aiosqlite:///:memory:"))
    )


def test_health_and_readiness_are_served() -> None:
    with TestClient(_create_test_app()) as client:
        health_response = client.get("/v1/health")
        readiness_response = client.get("/v1/readiness")

    assert health_response.json() == {"status": "ok"}
    assert readiness_response.json() == {"status": "ready"}


def test_readiness_is_unavailable_when_database_check_fails(monkeypatch) -> None:
    async def fail_database_check(self) -> None:
        raise OperationalError("SELECT 1", {}, RuntimeError("database unavailable"))

    monkeypatch.setattr(DatabaseReadinessCheck, "check", fail_database_check)

    with TestClient(_create_test_app()) as client:
        response = client.get("/v1/readiness")

    assert response.status_code == 503
    assert response.json() == {"detail": "Gateway dependencies are unavailable."}
