from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status

from sandbox_manager.docker_gateway import DockerSdkGateway
from sandbox_manager.files import WorkspaceFiles
from sandbox_manager.lifecycle import SandboxManager
from sandbox_manager.models import (
    ExecRequest,
    ExecResponse,
    FileEditRequest,
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

    @app.put("/v1/workspaces/{workspace_id}/sandbox", dependencies=[auth])
    async def ensure(workspace_id: str) -> SandboxResponse:
        return SandboxResponse(
            workspace_id=workspace_id,
            container_id=await manager.ensure(workspace_id),
        )

    @app.delete(
        "/v1/workspaces/{workspace_id}/sandbox",
        dependencies=[auth],
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def stop(workspace_id: str) -> Response:
        await manager.stop(workspace_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post("/v1/workspaces/{workspace_id}/exec", dependencies=[auth])
    async def execute(workspace_id: str, request: ExecRequest) -> ExecResponse:
        result = await manager.execute(workspace_id, request)
        return ExecResponse(
            exit_code=result.exit_code,
            stdout=result.stdout.decode(errors="replace"),
            stderr=result.stderr.decode(errors="replace"),
            timed_out=result.timed_out,
        )

    @app.get("/v1/workspaces/{workspace_id}/files/{path:path}", dependencies=[auth])
    async def read_file(workspace_id: str, path: str) -> Response:
        del workspace_id
        return Response(await files.read(path), media_type="text/plain")

    @app.get("/v1/workspaces/{workspace_id}/entries", dependencies=[auth])
    async def list_files(
        workspace_id: str,
        path: str = ".",
        recursive: bool = False,
    ) -> list[dict[str, object]]:
        del workspace_id
        entries = await files.list_entries(path, recursive=recursive)
        return [asdict(entry) for entry in entries]

    @app.get("/v1/workspaces/{workspace_id}/glob", dependencies=[auth])
    async def glob_files(workspace_id: str, pattern: str) -> list[dict[str, object]]:
        del workspace_id
        return [asdict(entry) for entry in await files.glob(pattern)]

    @app.post("/v1/workspaces/{workspace_id}/grep", dependencies=[auth])
    async def grep_files(
        workspace_id: str,
        request: GrepRequest,
    ) -> list[dict[str, object]]:
        del workspace_id
        matches = await files.grep(
            request.pattern,
            glob=request.glob,
            case_sensitive=request.case_sensitive,
            context_lines=request.context_lines,
            max_matches=request.max_matches,
        )
        return [asdict(match) for match in matches]

    @app.get("/v1/workspaces/{workspace_id}/stat", dependencies=[auth])
    async def stat_file(workspace_id: str, path: str) -> dict[str, object] | None:
        del workspace_id
        entry = await files.stat(path)
        return None if entry is None else asdict(entry)

    @app.put("/v1/workspaces/{workspace_id}/files/{path:path}", dependencies=[auth])
    async def write_file(
        workspace_id: str,
        path: str,
        request: FileWriteRequest,
    ) -> Response:
        del workspace_id
        await files.write(path, request.content)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post("/v1/workspaces/{workspace_id}/edit/{path:path}", dependencies=[auth])
    async def edit_file(
        workspace_id: str,
        path: str,
        request: FileEditRequest,
    ) -> dict[str, int]:
        del workspace_id
        count = await files.edit(
            path,
            request.old,
            request.new,
            replace_all=request.replace_all,
        )
        return {"count": count}

    return app


app = create_app()
