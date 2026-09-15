import asyncio
from collections.abc import Mapping, Sequence

from sandbox_manager.docker_gateway import ExecOutcome
from sandbox_manager.lifecycle import SandboxManager
from sandbox_manager.models import ExecRequest
from sandbox_manager.settings import SandboxManagerSettings


class _Docker:
    def __init__(self) -> None:
        self.created: list[str] = []
        self.removed: list[str] = []
        self.executed: list[tuple[str, tuple[str, ...]]] = []
        self.closed = False

    def create(self, workspace_id: str) -> str:
        self.created.append(workspace_id)
        return f"container-{len(self.created)}"

    def execute(
        self,
        container_id: str,
        argv: Sequence[str],
        *,
        cwd: str,
        env: Mapping[str, str],
        stdin: bytes | None,
    ) -> ExecOutcome:
        del cwd, env, stdin
        self.executed.append((container_id, tuple(argv)))
        return ExecOutcome(0, b"ok", b"")

    def remove(self, container_id: str) -> None:
        self.removed.append(container_id)

    def remove_owned(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


def _settings(**overrides: object) -> SandboxManagerSettings:
    return SandboxManagerSettings.model_validate(
        {
            "token": "test-token",
            "idle_ttl_seconds": 60,
            "reap_interval_seconds": 60,
            **overrides,
        }
    )


async def test_ensure_is_single_flight_per_workspace() -> None:
    docker = _Docker()
    manager = SandboxManager(docker, _settings())

    containers = await asyncio.gather(*(manager.ensure("default") for _ in range(8)))

    assert containers == ["container-1"] * 8
    assert docker.created == ["default"]
    await manager.close()


async def test_sessions_share_the_workspace_sandbox() -> None:
    docker = _Docker()
    manager = SandboxManager(docker, _settings())

    first = await manager.execute("default", ExecRequest(argv=("echo", "one")))
    second = await manager.execute("default", ExecRequest(argv=("echo", "two")))

    assert first.stdout == second.stdout == b"ok"
    assert docker.created == ["default"]
    assert [container for container, _ in docker.executed] == [
        "container-1",
        "container-1",
    ]
    await manager.close()


async def test_idle_sandbox_is_reaped() -> None:
    docker = _Docker()
    manager = SandboxManager(
        docker,
        _settings(idle_ttl_seconds=0.01, reap_interval_seconds=0.01),
    )
    await manager.start()
    await manager.ensure("default")

    await asyncio.sleep(0.04)

    assert docker.removed == ["container-1"]
    await manager.close()
