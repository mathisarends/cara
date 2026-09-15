from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import PlainTextResponse

from sandbox_manager.docker_gateway import DockerSdkGateway
from sandbox_manager.files import FileEntry, FileMatch, WorkspaceFiles
from sandbox_manager.lifecycle import SandboxManager
from sandbox_manager.models import (
    ExecRequest,
    ExecResponse,
    FileEditRequest,
    FileEditResponse,
    FileWriteRequest,
    GrepRequest,
    SandboxResponse,
)
from sandbox_manager.settings import SandboxManagerSettings


def create_app(settings: SandboxManagerSettings | None = None) -> FastAPI:
    selected = settings or SandboxManagerSettings()
    manager = SandboxManager(DockerSdkGateway(selected), selected)
    files = WorkspaceFiles(selected.workspace_root)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await manager.start()
        try:
            yield
        finally:
            await manager.close()

    app = FastAPI(title="Cara Sandbox Manager", version="1", lifespan=lifespan)

    async def authorize(authorization: str = Header()) -> None:
        expected = f"Bearer {selected.token.get_secret_value()}"
        if authorization != expected:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")

    auth = Depends(authorize)

    @app.exception_handler(FileNotFoundError)
    async def _handle_not_found(
        _: Request, exc: FileNotFoundError
    ) -> PlainTextResponse:
        return PlainTextResponse(str(exc), status_code=status.HTTP_404_NOT_FOUND)

    @app.exception_handler(PermissionError)
    async def _handle_forbidden(_: Request, exc: PermissionError) -> PlainTextResponse:
        return PlainTextResponse(str(exc), status_code=status.HTTP_403_FORBIDDEN)

    @app.exception_handler(NotADirectoryError)
    @app.exception_handler(ValueError)
    async def _handle_bad_request(_: Request, exc: Exception) -> PlainTextResponse:
        return PlainTextResponse(str(exc), status_code=status.HTTP_400_BAD_REQUEST)

    @app.put(
        "/v1/workspaces/{workspace_id}/sandbox",
        dependencies=[auth],
        operation_id="ensure_sandbox",
    )
    async def ensure(workspace_id: str) -> SandboxResponse:
        return SandboxResponse(
            workspace_id=workspace_id,
            container_id=await manager.ensure(workspace_id),
        )

    @app.delete(
        "/v1/workspaces/{workspace_id}/sandbox",
        dependencies=[auth],
        status_code=status.HTTP_204_NO_CONTENT,
        operation_id="stop_sandbox",
    )
    async def stop(workspace_id: str) -> None:
        await manager.stop(workspace_id)

    @app.post(
        "/v1/workspaces/{workspace_id}/exec",
        dependencies=[auth],
        operation_id="execute",
    )
    async def execute(workspace_id: str, request: ExecRequest) -> ExecResponse:
        result = await manager.execute(workspace_id, request)
        return ExecResponse(
            exit_code=result.exit_code,
            stdout=result.stdout.decode(errors="replace"),
            stderr=result.stderr.decode(errors="replace"),
            timed_out=result.timed_out,
        )

    @app.get(
        "/v1/workspaces/{workspace_id}/files/{file_path:path}",
        dependencies=[auth],
        response_class=PlainTextResponse,
        operation_id="read_file",
    )
    async def read_file(workspace_id: str, file_path: str) -> str:
        del workspace_id
        return await files.read(file_path)

    @app.get(
        "/v1/workspaces/{workspace_id}/entries",
        dependencies=[auth],
        operation_id="list_entries",
    )
    async def list_files(
        workspace_id: str,
        directory: str = ".",
        recursive: bool = False,
    ) -> list[FileEntry]:
        del workspace_id
        return await files.list_entries(directory, recursive=recursive)

    @app.get(
        "/v1/workspaces/{workspace_id}/glob",
        dependencies=[auth],
        operation_id="glob_files",
    )
    async def glob_files(workspace_id: str, pattern: str) -> list[FileEntry]:
        del workspace_id
        return await files.glob(pattern)

    @app.post(
        "/v1/workspaces/{workspace_id}/grep",
        dependencies=[auth],
        operation_id="grep_files",
    )
    async def grep_files(
        workspace_id: str,
        request: GrepRequest,
    ) -> list[FileMatch]:
        del workspace_id
        return await files.grep(
            request.pattern,
            glob=request.glob,
            case_sensitive=request.case_sensitive,
            context_lines=request.context_lines,
            max_matches=request.max_matches,
        )

    @app.get(
        "/v1/workspaces/{workspace_id}/stat",
        dependencies=[auth],
        operation_id="stat_file",
    )
    async def stat_file(workspace_id: str, file_path: str) -> FileEntry | None:
        del workspace_id
        return await files.stat(file_path)

    @app.put(
        "/v1/workspaces/{workspace_id}/files/{file_path:path}",
        dependencies=[auth],
        status_code=status.HTTP_204_NO_CONTENT,
        operation_id="write_file",
    )
    async def write_file(
        workspace_id: str,
        file_path: str,
        request: FileWriteRequest,
    ) -> None:
        del workspace_id
        await files.write(file_path, request.content)

    @app.post(
        "/v1/workspaces/{workspace_id}/edit/{file_path:path}",
        dependencies=[auth],
        operation_id="edit_file",
    )
    async def edit_file(
        workspace_id: str,
        file_path: str,
        request: FileEditRequest,
    ) -> FileEditResponse:
        del workspace_id
        count = await files.edit(
            file_path,
            request.old,
            request.new,
            replace_all=request.replace_all,
        )
        return FileEditResponse(count=count)

    return app


app = create_app()
