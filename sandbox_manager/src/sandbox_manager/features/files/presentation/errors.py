from fastapi_canon import Error, ErrorRegistry

from sandbox_manager.features.files.application import (
    InvalidEditError,
    PathOutsideWorkspaceError,
    WorkspaceFileNotFoundError,
    WorkspaceNotADirectoryError,
)

FILE_NOT_FOUND = Error(
    WorkspaceFileNotFoundError,
    status=404,
    code="file_not_found",
    title="File not found",
    detail=str,
)

PATH_OUTSIDE_WORKSPACE = Error(
    PathOutsideWorkspaceError,
    status=403,
    code="path_outside_workspace",
    title="Path outside workspace",
    detail=str,
)

NOT_A_DIRECTORY = Error(
    WorkspaceNotADirectoryError,
    status=400,
    code="not_a_directory",
    title="Not a directory",
    detail=str,
)

INVALID_EDIT = Error(
    InvalidEditError,
    status=400,
    code="invalid_edit",
    title="Invalid edit",
    detail=str,
)

FILES_ERRORS = ErrorRegistry(
    name="files",
    errors=[FILE_NOT_FOUND, PATH_OUTSIDE_WORKSPACE, NOT_A_DIRECTORY, INVALID_EDIT],
)
