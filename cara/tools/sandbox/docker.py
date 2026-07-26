import asyncio
import os
import uuid

from cara.tools.sandbox.models import BashSandboxMount, BashSandboxRequest, BashSandboxResult
from cara.tools.sandbox.ports import BashSandboxError


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
    """Run Bash in a short-lived Docker container."""

    def __init__(
        self,
        *,
        executable: str = "docker",
        timeout_seconds: float = 15.0,
        max_output_bytes: int = 1_000_000,
    ) -> None:
        if not executable:
            raise ValueError("Docker executable must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("Bash sandbox timeout must be positive")
        if max_output_bytes < 1:
            raise ValueError("Bash sandbox output limit must be positive")
        self._executable = executable
        self._timeout_seconds = timeout_seconds
        self._max_output_bytes = max_output_bytes

    async def run(self, request: BashSandboxRequest) -> BashSandboxResult:
        await self._ensure_runtime_available(request.config.image)
        container_name = f"cara-bash-{uuid.uuid4().hex}"
        process = await asyncio.create_subprocess_exec(
            *self._docker_arguments(container_name, request),
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
                f"the image '{request.config.image}' is installed.{detail}"
            )
        return BashSandboxResult(return_code=return_code, output=content)

    async def _ensure_runtime_available(self, image: str) -> None:
        try:
            process = await asyncio.create_subprocess_exec(
                self._executable,
                "image",
                "inspect",
                image,
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
                f"'{image}' is installed.{detail}"
            )

    def _docker_arguments(self, container_name: str, request: BashSandboxRequest) -> tuple[str, ...]:
        workspace_mount = f"type=bind,source={request.workspace.root},target=/workspace"
        arguments = [
            self._executable,
            "run",
            "--rm",
            "--name",
            container_name,
            "--pull=never",
            f"--network={request.config.network}",
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
            f"--mount={workspace_mount}",
        ]
        arguments.extend(f"--env={name}" for name in request.config.forwarded_environment if name in os.environ)
        arguments.extend(f"--mount={_format_mount(mount)}" for mount in request.config.mounts)
        arguments.extend(
            (
                request.config.image,
                "bash",
                "-lc",
                request.command,
            )
        )
        return tuple(arguments)

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


def _format_mount(mount: BashSandboxMount) -> str:
    option = f"type=bind,source={mount.source},target={mount.target}"
    return f"{option},readonly" if mount.read_only else option
