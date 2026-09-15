from pyrpckit import Inject, RpcInternalError, RpcInvalidParamsError, RpcModule

from gateway.features.automation.application import SessionAutomationService
from gateway.features.automation.presentation.rpc.mapping import (
    automation_origin,
    automation_response,
    automation_schedule,
    prompt_action,
)
from gateway.features.automation.presentation.rpc.models import (
    AutomationResponse,
    AutomationRpcMethod,
    CreateAutomationParams,
    DeleteAutomationParams,
    DeleteAutomationResponse,
    GetAutomationParams,
    ListAutomationsParams,
    ListAutomationsResponse,
    UpdateAutomationParams,
)
from gateway.presentation.rpc.errors import ResourceNotFoundError

automation_module = RpcModule()


@automation_module.method(AutomationRpcMethod.LIST, errors=(RpcInternalError,))
async def list_automations(
    params: ListAutomationsParams,
    service: Inject[SessionAutomationService],
) -> ListAutomationsResponse:
    """List automations belonging to a conversation session."""
    automations = await service.list(params.session_id)
    return ListAutomationsResponse(
        automations=tuple(automation_response(item) for item in automations)
    )


@automation_module.method(
    AutomationRpcMethod.GET, errors=(ResourceNotFoundError, RpcInternalError)
)
async def get_automation(
    params: GetAutomationParams,
    service: Inject[SessionAutomationService],
) -> AutomationResponse:
    automation = await service.get(params.automation_id, params.session_id)
    return automation_response(automation)


@automation_module.method(
    AutomationRpcMethod.CREATE, errors=(RpcInvalidParamsError, RpcInternalError)
)
async def create_automation(
    params: CreateAutomationParams,
    service: Inject[SessionAutomationService],
) -> AutomationResponse:
    automation = await service.create(
        params.session_id,
        schedule=automation_schedule(params.schedule),
        action=prompt_action(params.payload),
        origin=automation_origin(params.payload),
        name=params.name,
    )
    return automation_response(automation)


@automation_module.method(
    AutomationRpcMethod.UPDATE,
    errors=(ResourceNotFoundError, RpcInvalidParamsError, RpcInternalError),
)
async def update_automation(
    params: UpdateAutomationParams,
    service: Inject[SessionAutomationService],
) -> AutomationResponse:
    automation = await service.update(
        params.automation_id,
        params.session_id,
        schedule=automation_schedule(params.schedule),
        action=prompt_action(params.payload),
        origin=automation_origin(params.payload),
        name=params.name,
    )
    return automation_response(automation)


@automation_module.method(
    AutomationRpcMethod.DELETE, errors=(ResourceNotFoundError, RpcInternalError)
)
async def delete_automation(
    params: DeleteAutomationParams,
    service: Inject[SessionAutomationService],
) -> DeleteAutomationResponse:
    await service.delete(params.automation_id, params.session_id)
    return DeleteAutomationResponse(deleted=params.automation_id)
