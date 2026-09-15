from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import Depends
from fastapi.responses import PlainTextResponse
from fastapi_canon import CanonResponse, CanonRouter

from sandbox_manager.features.files.application import WorkspaceFileService
from sandbox_manager.features.files.presentation.errors import (
    FILE_NOT_FOUND,
    FILES_ERRORS,
    INVALID_EDIT,
    NOT_A_DIRECTORY,
    PATH_OUTSIDE_WORKSPACE,
)
from sandbox_manager.features.files.presentation.mapper import (
    to_file_entries,
    to_file_entry,
    to_file_matches,
)
from sandbox_manager.features.files.presentation.schemas import (
    FileEditRequest,
    FileEditResponse,
    FileEntry,
    FileMatch,
    FileWriteRequest,
    GrepRequest,
)
from sandbox_manager.presentation import require_token

# Every workspace currently shares the manager's single workspace root, so the
# routes accept workspace_id for a stable contract but do not scope by it yet.
files_router = CanonRouter(
    prefix="/v1/workspaces/{workspace_id}",
    tags=["files"],
    route_class=DishkaRoute,
    error_registry=FILES_ERRORS,
    dependencies=[Depends(require_token)],
)


@files_router.get(
    "/files/{file_path:path}",
    operation_id="read_file",
    response_class=PlainTextResponse,
    summary="Read a UTF-8 text file",
    raises=[FILE_NOT_FOUND, PATH_OUTSIDE_WORKSPACE],
)
async def read_file(
    workspace_id: str,
    file_path: str,
    service: FromDishka[WorkspaceFileService],
) -> str:
    del workspace_id
    return await service.read(file_path)


@files_router.put(
    "/files/{file_path:path}",
    operation_id="write_file",
    summary="Write a UTF-8 text file, creating parent directories",
    raises=[PATH_OUTSIDE_WORKSPACE],
    response=CanonResponse.empty(description="The file was written."),
)
async def write_file(
    workspace_id: str,
    file_path: str,
    request: FileWriteRequest,
    service: FromDishka[WorkspaceFileService],
) -> None:
    del workspace_id
    await service.write(file_path, request.content)


@files_router.post(
    "/edit/{file_path:path}",
    operation_id="edit_file",
    response_model=FileEditResponse,
    summary="Replace text in a file",
    raises=[FILE_NOT_FOUND, PATH_OUTSIDE_WORKSPACE, INVALID_EDIT],
)
async def edit_file(
    workspace_id: str,
    file_path: str,
    request: FileEditRequest,
    service: FromDishka[WorkspaceFileService],
) -> FileEditResponse:
    del workspace_id
    count = await service.edit(
        file_path,
        request.old,
        request.new,
        replace_all=request.replace_all,
    )
    return FileEditResponse(count=count)


@files_router.get(
    "/entries",
    operation_id="list_entries",
    response_model=list[FileEntry],
    summary="List a directory",
    raises=[PATH_OUTSIDE_WORKSPACE, NOT_A_DIRECTORY],
)
async def list_entries(
    workspace_id: str,
    service: FromDishka[WorkspaceFileService],
    directory: str = ".",
    recursive: bool = False,
) -> list[FileEntry]:
    del workspace_id
    entries = await service.list_entries(directory, recursive=recursive)
    return to_file_entries(entries)


@files_router.get(
    "/glob",
    operation_id="glob_files",
    response_model=list[FileEntry],
    summary="Find paths matching a glob pattern",
    raises=[PATH_OUTSIDE_WORKSPACE],
)
async def glob_files(
    workspace_id: str,
    pattern: str,
    service: FromDishka[WorkspaceFileService],
) -> list[FileEntry]:
    del workspace_id
    return to_file_entries(await service.glob(pattern))


@files_router.post(
    "/grep",
    operation_id="grep_files",
    response_model=list[FileMatch],
    summary="Search file contents with a regular expression",
)
async def grep_files(
    workspace_id: str,
    request: GrepRequest,
    service: FromDishka[WorkspaceFileService],
) -> list[FileMatch]:
    del workspace_id
    matches = await service.grep(
        request.pattern,
        glob=request.glob,
        case_sensitive=request.case_sensitive,
        context_lines=request.context_lines,
        max_matches=request.max_matches,
    )
    return to_file_matches(matches)


@files_router.get(
    "/stat",
    operation_id="stat_file",
    response_model=FileEntry | None,
    summary="Describe a path, or return null if it does not exist",
    raises=[PATH_OUTSIDE_WORKSPACE],
)
async def stat_file(
    workspace_id: str,
    file_path: str,
    service: FromDishka[WorkspaceFileService],
) -> FileEntry | None:
    del workspace_id
    entry = await service.stat(file_path)
    return None if entry is None else to_file_entry(entry)
