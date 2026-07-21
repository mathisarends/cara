import asyncio
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from cara.file_system import Workspace


class BashSandboxError(RuntimeError):
    """Failure to start or control the Bash sandbox."""


@dataclass(frozen=True)
class BashSandboxResult:
    return_code: int
    output: str


class BashSandbox(Protocol):
    async def run(self, command: str, workspace: Workspace) -> BashSandboxResult: ...


async def _read_limited_output(
    stream: asyncio.StreamReader,
    max_bytes: int,
) -> tuple[bytes, bool]:
    collected = bytearray()
    truncated = False
    while chunk := await stream.read(64 * 1024):
        remaining = max_bytes - len(collected)
        if remaining > 0:
            collected.extend(chunk[:remaining])
        if len(chunk) > remaining:
            truncated = True
    return bytes(collected), truncated


class DockerBashSandbox:
    """Run Bash in a short-lived, networkless Docker container."""

    def __init__(
        self,
        *,
        image: str = "cara-bash-sandbox:latest",
        executable: str = "docker",
        timeout_seconds: float = 15.0,
        max_output_bytes: int = 1_000_000,
    ) -> None:
        if not image:
            raise ValueError("Docker sandbox image must not be empty")
        if not executable:
            raise ValueError("Docker executable must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("Bash sandbox timeout must be positive")
        if max_output_bytes < 1:
            raise ValueError("Bash sandbox output limit must be positive")
        self._image = image
        self._executable = executable
        self._timeout_seconds = timeout_seconds
        self._max_output_bytes = max_output_bytes

    async def run(self, command: str, workspace: Workspace) -> BashSandboxResult:
        await self._ensure_runtime_available()
        container_name = f"cara-bash-{uuid.uuid4().hex}"
        process = await asyncio.create_subprocess_exec(
            *self._docker_arguments(container_name, command, workspace.root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        if process.stdout is None:
            process.kill()
            await process.wait()
            raise BashSandboxError("Docker started without an output stream.")

        output_task = asyncio.create_task(_read_limited_output(process.stdout, self._max_output_bytes))
        try:
            async with asyncio.timeout(self._timeout_seconds):
                return_code = await process.wait()
                output, truncated = await output_task
        except TimeoutError as error:
            process.kill()
            await process.wait()
            if not output_task.done():
                output_task.cancel()
            await self._remove_container(container_name)
            raise BashSandboxError(f"Bash sandbox exceeded its {self._timeout_seconds:g}-second time limit.") from error

        content = output.decode("utf-8", errors="replace").rstrip()
        if truncated:
            content += f"\n[Output truncated after {self._max_output_bytes} bytes.]"
        if return_code == 125:
            detail = f"\n{content}" if content else ""
            raise BashSandboxError(
                "Docker could not start the Bash sandbox. Ensure Docker Desktop is running and "
                f"the image '{self._image}' is installed.{detail}"
            )
        return BashSandboxResult(return_code=return_code, output=content)

    async def _ensure_runtime_available(self) -> None:
        try:
            process = await asyncio.create_subprocess_exec(
                self._executable,
                "image",
                "inspect",
                self._image,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except FileNotFoundError as error:
            raise BashSandboxError(
                "Docker is required for the Bash sandbox, but the Docker executable was not found."
            ) from error

        try:
            async with asyncio.timeout(5):
                output, _ = await process.communicate()
        except TimeoutError as error:
            process.kill()
            await process.wait()
            raise BashSandboxError("Docker did not respond while preparing the Bash sandbox.") from error

        if process.returncode != 0:
            content = output.decode("utf-8", errors="replace").rstrip()
            detail = f"\n{content}" if content else ""
            raise BashSandboxError(
                "The Bash sandbox is unavailable. Start Docker Desktop and make sure the image "
                f"'{self._image}' is installed.{detail}"
            )

    def _docker_arguments(self, container_name: str, command: str, workspace: Path) -> tuple[str, ...]:
        mount = f"type=bind,source={workspace},target=/workspace"
        return (
            self._executable,
            "run",
            "--rm",
            "--name",
            container_name,
            "--pull=never",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges=true",
            "--pids-limit=64",
            "--memory=256m",
            "--cpus=1",
            "--ulimit=nofile=256:256",
            "--ipc=none",
            "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=64m",
            "--env=HOME=/tmp",
            "--workdir=/workspace",
            f"--mount={mount}",
            self._image,
            "bash",
            "-lc",
            command,
        )

    async def _remove_container(self, container_name: str) -> None:
        try:
            process = await asyncio.create_subprocess_exec(
                self._executable,
                "rm",
                "--force",
                container_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except FileNotFoundError:
            return
        await process.wait()
