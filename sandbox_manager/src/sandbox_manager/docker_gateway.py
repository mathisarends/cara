import contextlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

import docker
from docker.models.containers import Container

from sandbox_manager.settings import SandboxManagerSettings

_OWNER_LABEL = "dev.cara.sandbox-manager"
_WORKSPACE_LABEL = "dev.cara.workspace"


@dataclass(frozen=True, slots=True)
class ExecOutcome:
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool = False


class DockerGateway(Protocol):
    def create(self, workspace_id: str) -> str: ...

    def execute(
        self,
        container_id: str,
        argv: Sequence[str],
        *,
        cwd: str,
        env: Mapping[str, str],
        stdin: bytes | None,
    ) -> ExecOutcome: ...

    def remove(self, container_id: str) -> None: ...

    def remove_owned(self) -> None: ...

    def close(self) -> None: ...


class DockerSdkGateway:
    def __init__(self, settings: SandboxManagerSettings) -> None:
        self._settings = settings
        self._client = docker.from_env()

    def create(self, workspace_id: str) -> str:
        container = self._client.containers.run(
            self._settings.image,
            ["/bin/sh", "-c", "while :; do sleep 3600; done"],
            detach=True,
            auto_remove=True,
            init=True,
            read_only=True,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges"],
            tmpfs={"/tmp": "rw,nosuid,nodev"},
            working_dir="/workspace",
            environment={"HOME": "/tmp"},
            network_disabled=not self._settings.network_access,
            mem_limit=self._settings.memory_bytes,
            pids_limit=self._settings.pids,
            nano_cpus=int(self._settings.cpus * 1_000_000_000),
            volumes={
                self._settings.workspace_volume: {
                    "bind": "/workspace",
                    "mode": "rw",
                },
                self._settings.cli_config_volume: {
                    "bind": "/tmp/.config",
                    "mode": "rw",
                },
            },
            labels={_OWNER_LABEL: "true", _WORKSPACE_LABEL: workspace_id},
        )
        return container.id

    def execute(
        self,
        container_id: str,
        argv: Sequence[str],
        *,
        cwd: str,
        env: Mapping[str, str],
        stdin: bytes | None,
    ) -> ExecOutcome:
        container = self._container(container_id)
        if stdin is not None:
            raise ValueError("stdin is not supported by the Docker adapter yet")
        result = container.exec_run(
            list(argv),
            workdir=cwd,
            environment=dict(env),
            demux=True,
        )
        stdout, stderr = result.output
        return ExecOutcome(result.exit_code, stdout or b"", stderr or b"")

    def remove(self, container_id: str) -> None:
        with contextlib.suppress(docker.errors.NotFound):
            self._container(container_id).remove(force=True)

    def remove_owned(self) -> None:
        containers: list[Container] = self._client.containers.list(
            all=True,
            filters={"label": f"{_OWNER_LABEL}=true"},
        )
        for container in containers:
            container.remove(force=True)

    def close(self) -> None:
        self._client.close()

    def _container(self, container_id: str) -> Container:
        return self._client.containers.get(container_id)
