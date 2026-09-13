from pyrpckit import Inject, RpcInternalError, RpcInvalidParamsError, RpcModule

from gateway.features.automation.presentation.rpc.handler import AutomationRpcMethods
from gateway.features.automation.presentation.rpc.schemas import (
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
    handler: Inject[AutomationRpcMethods],
) -> ListAutomationsResponse:
    return await handler.list_automations(params)


@automation_module.method(
    AutomationRpcMethod.GET, errors=(ResourceNotFoundError, RpcInternalError)
)
async def get_automation(
    params: GetAutomationParams,
    handler: Inject[AutomationRpcMethods],
) -> AutomationResponse:
    return await handler.get_automation(params)


@automation_module.method(
    AutomationRpcMethod.CREATE, errors=(RpcInvalidParamsError, RpcInternalError)
)
async def create_automation(
    params: CreateAutomationParams,
    handler: Inject[AutomationRpcMethods],
) -> AutomationResponse:
    return await handler.create_automation(params)


@automation_module.method(
    AutomationRpcMethod.UPDATE,
    errors=(ResourceNotFoundError, RpcInvalidParamsError, RpcInternalError),
)
async def update_automation(
    params: UpdateAutomationParams,
    handler: Inject[AutomationRpcMethods],
) -> AutomationResponse:
    return await handler.update_automation(params)


@automation_module.method(
    AutomationRpcMethod.DELETE, errors=(ResourceNotFoundError, RpcInternalError)
)
async def delete_automation(
    params: DeleteAutomationParams,
    handler: Inject[AutomationRpcMethods],
) -> DeleteAutomationResponse:
    return await handler.delete_automation(params)
