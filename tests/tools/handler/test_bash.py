import asyncio
from pathlib import Path

import pytest

from cara.file_system import Workspace
from cara.tools.handler import (
    BashSandboxConfig,
    BashSandboxError,
    BashSandboxMount,
    BashSandboxRequest,
    BashSandboxResult,
    DockerBashSandbox,
)


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


def _request(
    command: str,
    tmp_path: Path,
    *,
    config: BashSandboxConfig | None = None,
) -> BashSandboxRequest:
    return BashSandboxRequest(
        command=command,
        workspace=Workspace(tmp_path),
        config=config or BashSandboxConfig(),
    )


def test_docker_sandbox_runs_command_with_isolation_flags(monkeypatch, tmp_path: Path) -> None:
    invocations: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def create_process(*args, **kwargs):
        invocations.append((args, kwargs))
        if args[1:3] == ("image", "inspect"):
            return _Process(b"image details")
        return _Process(b"sandbox output\n")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)

    config = BashSandboxConfig(image="custom-bash:local", network="bridge")
    result = asyncio.run(DockerBashSandbox().run(_request("echo hello | sed s/h/H/", tmp_path, config=config)))

    assert result == BashSandboxResult(return_code=0, output="sandbox output")
    assert invocations[0][0][0:4] == ("docker", "image", "inspect", "custom-bash:local")
    arguments, kwargs = invocations[1]
    assert arguments[0:2] == ("docker", "run")
    assert "--pull=never" in arguments
    assert "--network=bridge" in arguments
    assert "--read-only" in arguments
    assert "--cap-drop=ALL" in arguments
    assert "--security-opt=no-new-privileges=true" in arguments
    assert "--pids-limit=64" in arguments
    assert "--memory=256m" in arguments
    assert "--cpus=1" in arguments
    assert "--ipc=none" in arguments
    assert f"--mount=type=bind,source={tmp_path.resolve()},target=/workspace" in arguments
    assert arguments[-4] == "custom-bash:local"
    assert arguments[-3:] == ("bash", "-lc", "echo hello | sed s/h/H/")
    assert kwargs["stderr"] is asyncio.subprocess.STDOUT


def test_docker_sandbox_forwards_spotify_credentials_without_command_line_values(
    monkeypatch,
    tmp_path: Path,
) -> None:
    invocations: list[tuple[tuple[object, ...], dict[str, object]]] = []
    cache_path = tmp_path / "spotify.cache"
    cache_path.write_text("{}")
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "client-id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "super-secret")

    async def create_process(*args, **kwargs):
        invocations.append((args, kwargs))
        if args[1:3] == ("image", "inspect"):
            return _Process(b"image details")
        return _Process(b"spotify output\n")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)

    config = BashSandboxConfig(
        network="bridge",
        forwarded_environment=("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"),
        mounts=(BashSandboxMount(cache_path, "/workspace/.cache", read_only=False),),
    )
    result = asyncio.run(DockerBashSandbox().run(_request("spotifyify users me", tmp_path, config=config)))

    assert result == BashSandboxResult(return_code=0, output="spotify output")
    arguments = invocations[1][0]
    assert "--env=SPOTIFY_CLIENT_ID" in arguments
    assert "--env=SPOTIFY_CLIENT_SECRET" in arguments
    assert "client-id" not in arguments
    assert "super-secret" not in arguments
    assert f"--mount=type=bind,source={cache_path.resolve()},target=/workspace/.cache" in arguments


def test_docker_sandbox_does_not_forward_unset_credentials(monkeypatch, tmp_path: Path) -> None:
    invocations: list[tuple[tuple[object, ...], dict[str, object]]] = []
    for name in (
        "SPOTIFY_CLIENT_ID",
        "SPOTIFY_CLIENT_SECRET",
        "SPOTIFY_REDIRECT_URI",
        "SPOTIFY_ACCESS_TOKEN",
        "SPOTIFY_REFRESH_TOKEN",
        "SPOTIFY_TOKEN_EXPIRES_AT",
    ):
        monkeypatch.delenv(name, raising=False)

    async def create_process(*args, **kwargs):
        invocations.append((args, kwargs))
        if args[1:3] == ("image", "inspect"):
            return _Process(b"image details")
        return _Process(b"output\n")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)

    config = BashSandboxConfig(
        forwarded_environment=(
            "SPOTIFY_CLIENT_ID",
            "SPOTIFY_CLIENT_SECRET",
            "SPOTIFY_REDIRECT_URI",
            "SPOTIFY_ACCESS_TOKEN",
            "SPOTIFY_REFRESH_TOKEN",
            "SPOTIFY_TOKEN_EXPIRES_AT",
        )
    )
    asyncio.run(DockerBashSandbox().run(_request("env", tmp_path, config=config)))

    arguments = invocations[1][0]
    assert not any(str(argument).startswith("--env=SPOTIFY_") for argument in arguments)


def test_sandbox_mount_is_read_only_by_default(tmp_path: Path) -> None:
    source = tmp_path / "config.json"
    source.write_text("{}")

    mount = BashSandboxMount(source, "/run/config.json")

    assert mount.source == source.resolve()
    assert mount.target == "/run/config.json"
    assert mount.read_only is True


def test_sandbox_mount_rejects_relative_container_target(tmp_path: Path) -> None:
    source = tmp_path / "config.json"
    source.write_text("{}")

    with pytest.raises(ValueError, match="absolute container path"):
        BashSandboxMount(source, "run/config.json")


def test_sandbox_config_rejects_invalid_environment_name() -> None:
    with pytest.raises(ValueError, match="Invalid environment variable names"):
        BashSandboxConfig(forwarded_environment=("VALID_NAME", "INVALID-NAME"))


def test_docker_sandbox_limits_captured_output(monkeypatch, tmp_path: Path) -> None:
    async def create_process(*args, **kwargs):
        if args[1:3] == ("image", "inspect"):
            return _Process(b"image details")
        return _Process(b"123456789")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)

    result = asyncio.run(DockerBashSandbox(max_output_bytes=4).run(_request("yes", tmp_path)))

    assert result.output == "1234\n[Output truncated after 4 bytes.]"


def test_docker_sandbox_reports_missing_executable(monkeypatch, tmp_path: Path) -> None:
    async def create_process(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)

    with pytest.raises(BashSandboxError, match="Docker executable was not found"):
        asyncio.run(DockerBashSandbox().run(_request("echo hello", tmp_path)))


def test_docker_sandbox_explains_startup_failure(monkeypatch, tmp_path: Path) -> None:
    async def create_process(*args, **kwargs):
        if args[1:3] == ("image", "inspect"):
            return _Process(b"image details")
        return _Process(b"daemon is not running", return_code=125)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)

    with pytest.raises(BashSandboxError, match="Ensure Docker Desktop is running"):
        asyncio.run(DockerBashSandbox().run(_request("echo hello", tmp_path)))


def test_docker_sandbox_explains_unavailable_runtime(monkeypatch, tmp_path: Path) -> None:
    async def create_process(*args, **kwargs):
        return _Process(b"error during connect", return_code=1)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)

    with pytest.raises(BashSandboxError, match="Start Docker Desktop"):
        asyncio.run(DockerBashSandbox().run(_request("echo hello", tmp_path)))
