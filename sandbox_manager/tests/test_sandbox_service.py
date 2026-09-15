import asyncio
from collections.abc import Mapping, Sequence

from sandbox_manager.features.sandbox.application import (
    ExecCommand,
    ExecOutcome,
    SandboxRuntime,
    SandboxService,
)
from sandbox_manager.features.sandbox.settings import SandboxSettings


class _Runtime(SandboxRuntime):
    def __init__(self) -> None:
        self.created: list[str] = []
        self.removed: list[str] = []
        self.executed: list[tuple[str, tuple[str, ...]]] = []

    def create(self, workspace_id: str) -> str:
        self.created.append(workspace_id)
        return f"sandbox-{len(self.created)}"

    def execute(
        self,
        sandbox_id: str,
        argv: Sequence[str],
        *,
        cwd: str,
        env: Mapping[str, str],
        stdin: bytes | None,
    ) -> ExecOutcome:
        del cwd, env, stdin
        self.executed.append((sandbox_id, tuple(argv)))
        return ExecOutcome(0, b"ok", b"")

    def remove(self, sandbox_id: str) -> None:
        self.removed.append(sandbox_id)

    def remove_owned(self) -> None:
        pass

    def is_available(self) -> bool:
        return True

    def close(self) -> None:
        pass


def _settings(**overrides: object) -> SandboxSettings:
    return SandboxSettings.model_validate(
        {
            "idle_ttl_seconds": 60,
            "reap_interval_seconds": 60,
            **overrides,
        }
    )


def _command(*argv: str) -> ExecCommand:
    return ExecCommand(
        argv=argv, cwd="/workspace", env={}, stdin=None, timeout_seconds=15
    )


async def test_ensure_is_single_flight_per_workspace() -> None:
    runtime = _Runtime()
    service = SandboxService(runtime, _settings())

    sandboxes = await asyncio.gather(*(service.ensure("default") for _ in range(8)))

    assert sandboxes == ["sandbox-1"] * 8
    assert runtime.created == ["default"]
    await service.close()


async def test_sessions_share_the_workspace_sandbox() -> None:
    runtime = _Runtime()
    service = SandboxService(runtime, _settings())

    first = await service.execute("default", _command("echo", "one"))
    second = await service.execute("default", _command("echo", "two"))

    assert first.stdout == second.stdout == b"ok"
    assert runtime.created == ["default"]
    assert [sandbox for sandbox, _ in runtime.executed] == ["sandbox-1", "sandbox-1"]
    await service.close()


async def test_idle_sandbox_is_reaped() -> None:
    runtime = _Runtime()
    service = SandboxService(
        runtime,
        _settings(idle_ttl_seconds=0.01, reap_interval_seconds=0.01),
    )
    await service.start()
    await service.ensure("default")

    await asyncio.sleep(0.04)

    assert runtime.removed == ["sandbox-1"]
    await service.close()
