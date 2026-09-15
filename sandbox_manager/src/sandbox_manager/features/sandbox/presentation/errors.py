from fastapi_canon import Error, ErrorRegistry

from sandbox_manager.features.sandbox.application import (
    InvalidWorkspaceIdError,
    StdinNotSupportedError,
)

INVALID_WORKSPACE_ID = Error(
    InvalidWorkspaceIdError,
    status=400,
    code="invalid_workspace_id",
    title="Invalid workspace id",
    detail=str,
)

STDIN_NOT_SUPPORTED = Error(
    StdinNotSupportedError,
    status=400,
    code="stdin_not_supported",
    title="Stdin not supported",
    detail=str,
)

SANDBOX_ERRORS = ErrorRegistry(
    name="sandbox",
    errors=[INVALID_WORKSPACE_ID, STDIN_NOT_SUPPORTED],
)
