from pathlib import Path

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from gateway import app
from scheduler import Scheduler


def test_health(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("GATEWAY_SCHEDULER_DATABASE_PATH", str(tmp_path / "jobs.sqlite3"))

    with TestClient(app) as client:
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert isinstance(app.state.scheduler, Scheduler)
        assert app.state.scheduler.running is True

    assert app.state.scheduler.running is False
