import asyncio
from pathlib import Path

import pytest

from cara.file_system import Workspace
from cara.tools.handler import BashSandboxError, BashSandboxResult, DockerBashSandbox


class _Process:
    def __init__(self, output: bytes, return_code: int = 0) -> None:
        self.stdout = asyncio.StreamReader()
        self.stdout.feed_data(output)
        self.stdout.feed_eof()
        self._return_code = return_code
        self.returncode = return_code
        self.killed = False

    async def wait(self) -> int:
        return self._return_code

    async def communicate(self) -> tuple[bytes, None]:
        output = await self.stdout.read()
        return output, None

    def kill(self) -> None:
        self.killed = True


def test_docker_sandbox_runs_command_with_isolation_flags(monkeypatch, tmp_path: Path) -> None:
    invocations: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def create_process(*args, **kwargs):
        invocations.append((args, kwargs))
        if args[1:3] == ("image", "inspect"):
            return _Process(b"image details")
        return _Process(b"sandbox output\n")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)

    result = asyncio.run(DockerBashSandbox().run("echo hello | sed s/h/H/", Workspace(tmp_path)))

    assert result == BashSandboxResult(return_code=0, output="sandbox output")
    assert invocations[0][0][0:4] == ("docker", "image", "inspect", "cara-bash-sandbox:latest")
    arguments, kwargs = invocations[1]
    assert arguments[0:2] == ("docker", "run")
    assert "--pull=never" in arguments
    assert "--network=none" in arguments
    assert "--read-only" in arguments
    assert "--cap-drop=ALL" in arguments
    assert "--security-opt=no-new-privileges=true" in arguments
    assert "--pids-limit=64" in arguments
    assert "--memory=256m" in arguments
    assert "--cpus=1" in arguments
    assert "--ipc=none" in arguments
    assert f"--mount=type=bind,source={tmp_path.resolve()},target=/workspace" in arguments
    assert arguments[-3:] == ("bash", "-lc", "echo hello | sed s/h/H/")
    assert kwargs["stderr"] is asyncio.subprocess.STDOUT


def test_docker_sandbox_limits_captured_output(monkeypatch, tmp_path: Path) -> None:
    async def create_process(*args, **kwargs):
        if args[1:3] == ("image", "inspect"):
            return _Process(b"image details")
        return _Process(b"123456789")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)

    result = asyncio.run(DockerBashSandbox(max_output_bytes=4).run("yes", Workspace(tmp_path)))

    assert result.output == "1234\n[Output truncated after 4 bytes.]"


def test_docker_sandbox_reports_missing_executable(monkeypatch, tmp_path: Path) -> None:
    async def create_process(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)

    with pytest.raises(BashSandboxError, match="Docker executable was not found"):
        asyncio.run(DockerBashSandbox().run("echo hello", Workspace(tmp_path)))


def test_docker_sandbox_explains_startup_failure(monkeypatch, tmp_path: Path) -> None:
    async def create_process(*args, **kwargs):
        if args[1:3] == ("image", "inspect"):
            return _Process(b"image details")
        return _Process(b"daemon is not running", return_code=125)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)

    with pytest.raises(BashSandboxError, match="Ensure Docker Desktop is running"):
        asyncio.run(DockerBashSandbox().run("echo hello", Workspace(tmp_path)))


def test_docker_sandbox_explains_unavailable_runtime(monkeypatch, tmp_path: Path) -> None:
    async def create_process(*args, **kwargs):
        return _Process(b"error during connect", return_code=1)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)

    with pytest.raises(BashSandboxError, match="Start Docker Desktop"):
        asyncio.run(DockerBashSandbox().run("echo hello", Workspace(tmp_path)))
