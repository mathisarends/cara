from collections.abc import Iterator
from pathlib import Path

import docker
import pytest
from fastapi.testclient import TestClient

from sandbox_manager.app import create_app


class _Containers:
    def list(self, **_: object) -> list[object]:
        return []


class _DockerClient:
    def __init__(self) -> None:
        self.containers = _Containers()
        self.available = True

    def ping(self) -> bool:
        if not self.available:
            raise docker.errors.APIError("docker daemon is unreachable")
        return True

    def close(self) -> None:
        pass


@pytest.fixture
def docker_client(monkeypatch: pytest.MonkeyPatch) -> _DockerClient:
    client = _DockerClient()
    monkeypatch.setattr(docker, "from_env", lambda: client)
    return client


@pytest.fixture
def workspace_root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def client(
    docker_client: _DockerClient,
    workspace_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    monkeypatch.setenv("CARA_SANDBOX_TOKEN", "test-token")
    monkeypatch.setenv("CARA_SANDBOX_WORKSPACE_ROOT", str(workspace_root))
    with TestClient(create_app()) as test_client:
        yield test_client


def test_health_and_readiness_are_served(client: TestClient) -> None:
    assert client.get("/v1/health").json() == {"status": "ok"}
    assert client.get("/v1/readiness").json() == {"status": "ready"}


def test_readiness_is_unavailable_when_the_runtime_is_unreachable(
    client: TestClient,
    docker_client: _DockerClient,
) -> None:
    docker_client.available = False

    response = client.get("/v1/readiness")

    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "dependency_unavailable"
    assert response.json()["detail"] == "sandbox runtime is unavailable"


@pytest.mark.parametrize("workspace_root", [Path("/does/not/exist")])
def test_readiness_is_unavailable_without_a_workspace_root(
    client: TestClient,
) -> None:
    response = client.get("/v1/readiness")

    assert response.status_code == 503
    assert response.json()["detail"] == "workspace root is unavailable"


def test_workspace_routes_reject_an_invalid_token(client: TestClient) -> None:
    response = client.get(
        "/v1/workspaces/default/entries",
        headers={"authorization": "Bearer wrong"},
    )

    assert response.status_code == 401


def test_workspace_errors_are_problem_details(
    client: TestClient,
    workspace_root: Path,
) -> None:
    response = client.get(
        "/v1/workspaces/default/files/missing.txt",
        headers={"authorization": "Bearer test-token"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "file_not_found"
