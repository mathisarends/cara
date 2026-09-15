import contextlib
from collections.abc import Mapping, Sequence
from pathlib import Path

import docker
from docker.models.containers import Container

from sandbox_manager.features.sandbox.application import (
    ExecOutcome,
    SandboxRuntime,
    StdinNotSupportedError,
)
from sandbox_manager.features.sandbox.settings import SandboxSettings

_OWNER_LABEL = "dev.cara.sandbox-manager"
_WORKSPACE_LABEL = "dev.cara.workspace"


class DockerSandboxRuntime(SandboxRuntime):
    def __init__(self, settings: SandboxSettings) -> None:
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
                **_credential_volumes(self._settings.cli_credential_mounts),
            },
            labels={_OWNER_LABEL: "true", _WORKSPACE_LABEL: workspace_id},
        )
        return container.id

    def execute(
        self,
        sandbox_id: str,
        argv: Sequence[str],
        *,
        cwd: str,
        env: Mapping[str, str],
        stdin: bytes | None,
    ) -> ExecOutcome:
        if stdin is not None:
            raise StdinNotSupportedError()
        result = self._container(sandbox_id).exec_run(
            list(argv),
            workdir=cwd,
            environment=dict(env),
            demux=True,
        )
        stdout, stderr = result.output
        return ExecOutcome(result.exit_code, stdout or b"", stderr or b"")

    def remove(self, sandbox_id: str) -> None:
        with contextlib.suppress(docker.errors.NotFound):
            self._container(sandbox_id).remove(force=True)

    def remove_owned(self) -> None:
        containers: list[Container] = self._client.containers.list(
            all=True,
            filters={"label": f"{_OWNER_LABEL}=true"},
        )
        for container in containers:
            container.remove(force=True)

    def is_available(self) -> bool:
        # requests' connection errors are OSErrors, not DockerExceptions.
        try:
            return self._client.ping()
        except (docker.errors.DockerException, OSError):
            return False

    def close(self) -> None:
        self._client.close()

    def _container(self, sandbox_id: str) -> Container:
        return self._client.containers.get(sandbox_id)


def _credential_volumes(mounts: Mapping[str, Path]) -> dict[str, dict[str, str]]:
    return {
        str(host_dir): {"bind": f"/tmp/.config/{name}", "mode": "rw"}
        for name, host_dir in mounts.items()
    }
