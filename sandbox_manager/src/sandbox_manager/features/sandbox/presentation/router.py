from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import Depends
from fastapi_canon import CanonResponse, CanonRouter

from sandbox_manager.features.sandbox.application import SandboxService
from sandbox_manager.features.sandbox.presentation.errors import (
    INVALID_WORKSPACE_ID,
    SANDBOX_ERRORS,
    STDIN_NOT_SUPPORTED,
)
from sandbox_manager.features.sandbox.presentation.mapper import (
    to_exec_command,
    to_exec_response,
    to_sandbox_response,
)
from sandbox_manager.features.sandbox.presentation.schemas import (
    ExecRequest,
    ExecResponse,
    SandboxResponse,
)
from sandbox_manager.presentation import require_token

sandbox_router = CanonRouter(
    prefix="/v1/workspaces/{workspace_id}",
    tags=["sandboxes"],
    route_class=DishkaRoute,
    error_registry=SANDBOX_ERRORS,
    dependencies=[Depends(require_token)],
)


@sandbox_router.put(
    "/sandbox",
    operation_id="ensure_sandbox",
    response_model=SandboxResponse,
    summary="Start the workspace sandbox unless it is already running",
    raises=[INVALID_WORKSPACE_ID],
)
async def ensure_sandbox(
    workspace_id: str,
    service: FromDishka[SandboxService],
) -> SandboxResponse:
    sandbox_id = await service.ensure(workspace_id)
    return to_sandbox_response(workspace_id, sandbox_id)


@sandbox_router.delete(
    "/sandbox",
    operation_id="stop_sandbox",
    summary="Stop the workspace sandbox",
    response=CanonResponse.empty(description="The sandbox is not running."),
)
async def stop_sandbox(
    workspace_id: str,
    service: FromDishka[SandboxService],
) -> None:
    await service.stop(workspace_id)


@sandbox_router.post(
    "/exec",
    operation_id="execute",
    response_model=ExecResponse,
    summary="Run a command in the workspace sandbox",
    raises=[INVALID_WORKSPACE_ID, STDIN_NOT_SUPPORTED],
)
async def execute(
    workspace_id: str,
    request: ExecRequest,
    service: FromDishka[SandboxService],
) -> ExecResponse:
    outcome = await service.execute(workspace_id, to_exec_command(request))
    return to_exec_response(outcome)
