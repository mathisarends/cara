import asyncio
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from agenttoolkit.builtins import CommandResult
from agenttoolkit.builtins.shell.backends import docker as docker_backend

from agent.sandbox import ManagedSandbox, SandboxDefinition, create_sandbox

_HANGING_COMMAND = "sonos status --ip 192.168.178.76"


@pytest.fixture
def fake_docker(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """Replaces the docker subprocess, optionally timing out on one command."""

    def install(*, hangs_on: str | None = None) -> None:
        async def run_process(
            argv: Sequence[str], *, command: str, **_: object
        ) -> CommandResult:
            timed_out = command == hangs_on
            return CommandResult(
                command=command,
                returncode=None if timed_out else 0,
                stdout="",
                stderr="",
                duration_seconds=0.0,
                timed_out=timed_out,
            )

        monkeypatch.setattr(docker_backend, "run_process", run_process)

    return install


def test_command_timeout_discards_the_container(
    project_sandbox: SandboxDefinition, tmp_path: Path, fake_docker
) -> None:
    fake_docker(hangs_on=_HANGING_COMMAND)
    sandbox = create_sandbox(tmp_path, project_sandbox)

    async def run() -> None:
        await sandbox.open()
        result = await sandbox.execute(_HANGING_COMMAND)

        assert result.timed_out
        assert not sandbox.is_open

    asyncio.run(run())


def test_next_command_reopens_the_discarded_container(
    project_sandbox: SandboxDefinition, tmp_path: Path, fake_docker
) -> None:
    fake_docker(hangs_on=_HANGING_COMMAND)
    sandbox = create_sandbox(tmp_path, project_sandbox)

    async def run() -> None:
        await sandbox.open()
        discarded = sandbox.container_name
        await sandbox.execute(_HANGING_COMMAND)

        result = await sandbox.execute("sonos status --ip 192.168.178.68")

        assert result.ok
        assert sandbox.is_open
        assert sandbox.container_name != discarded

    asyncio.run(run())


def test_first_command_opens_a_sandbox_that_was_never_opened(
    project_sandbox: SandboxDefinition, tmp_path: Path, fake_docker
) -> None:
    fake_docker()
    sandbox = create_sandbox(tmp_path, project_sandbox)

    async def run() -> None:
        result = await sandbox.execute("echo hello")

        assert result.ok
        assert sandbox.is_open

    asyncio.run(run())


def test_concurrent_commands_open_the_container_once(
    project_sandbox: SandboxDefinition, tmp_path: Path, fake_docker
) -> None:
    fake_docker()
    sandbox = create_sandbox(tmp_path, project_sandbox)

    async def run() -> None:
        await asyncio.gather(*(sandbox.execute("echo hello") for _ in range(5)))

        assert sandbox.is_open

    asyncio.run(run())


def test_create_sandbox_returns_a_managed_sandbox(
    project_sandbox: SandboxDefinition, tmp_path: Path
) -> None:
    assert isinstance(create_sandbox(tmp_path, project_sandbox), ManagedSandbox)
