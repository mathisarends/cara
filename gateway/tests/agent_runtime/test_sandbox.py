from pathlib import Path
from typing import cast

import httpx2
import pytest

from gateway.agent_runtime.sandbox import SandboxClientSettings, WorkspaceSandboxClient
from sandbox_manager_client import ApiError, ExecResponse, FileNotFoundProblem


class _SandboxManager:
    def __init__(self) -> None:
        self.ensure_arguments: tuple[str, str] | None = None
        self.execute_arguments: tuple[str, str, object, float] | None = None

    async def ensure_sandbox(self, workspace_id: str, authorization: str) -> None:
        self.ensure_arguments = workspace_id, authorization

    async def execute(
        self,
        workspace_id: str,
        authorization: str,
        request: object,
        *,
        timeout: float,
    ) -> ExecResponse:
        self.execute_arguments = workspace_id, authorization, request, timeout
        return ExecResponse(
            exit_code=0,
            stdout="done\n",
            stderr="",
            timed_out=False,
        )


class _MissingFileManager:
    async def read_file(self, workspace_id: str, path: str, authorization: str) -> str:
        detail = f"{workspace_id}:{path}:{authorization}"
        raise ApiError(
            404,
            detail,
            FileNotFoundProblem(
                type="urn:cara:sandbox-manager:problem/file_not_found",
                title="File not found",
                status=404,
                code="file_not_found",
                detail=detail,
            ),
        )


def _client(tmp_path: Path, manager: object) -> WorkspaceSandboxClient:
    http_client = cast(httpx2.AsyncClient, object())
    client = WorkspaceSandboxClient(
        SandboxClientSettings(token="secret", workspace_id="primary"),
        tmp_path,
        client=http_client,
    )
    client._client = manager
    return client


async def test_remote_sandbox_is_ensured_and_executes_commands(tmp_path: Path) -> None:
    manager = _SandboxManager()
    client = _client(tmp_path, manager)

    await client.ensure()
    result = await client.execute(
        "pwd",
        cwd="project",
        env={"MODE": "test"},
        stdin=b"input",
        timeout=7,
    )

    assert manager.ensure_arguments == ("primary", "Bearer secret")
    assert manager.execute_arguments is not None
    workspace_id, authorization, request, timeout = manager.execute_arguments
    assert workspace_id == "primary"
    assert authorization == "Bearer secret"
    assert request.argv == ["/bin/bash", "-lc", "pwd"]
    assert request.cwd == "/workspace/project"
    assert request.env == {"MODE": "test"}
    assert request.stdin == "input"
    assert timeout == 12
    assert result.output == "done\n"


async def test_remote_not_found_is_exposed_as_workspace_error(tmp_path: Path) -> None:
    client = _client(tmp_path, _MissingFileManager())

    with pytest.raises(FileNotFoundError, match="primary:notes.txt:Bearer secret"):
        await client.read_file("notes.txt")
