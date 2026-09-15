import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from gateway.features.health.infrastructure import DatabaseReadinessCheck


def test_health_and_readiness_are_served(client: TestClient) -> None:
    health_response = client.get("/v1/health")
    readiness_response = client.get("/v1/readiness")

    assert health_response.json() == {"status": "ok"}
    assert readiness_response.json() == {"status": "ready"}


def test_readiness_is_unavailable_when_database_check_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_database_check(self) -> None:
        raise OperationalError("SELECT 1", {}, RuntimeError("database unavailable"))

    monkeypatch.setattr(DatabaseReadinessCheck, "check", fail_database_check)

    response = client.get("/v1/readiness")

    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["detail"] == "Gateway dependencies are unavailable."
