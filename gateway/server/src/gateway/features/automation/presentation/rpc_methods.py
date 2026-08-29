from pyrpckit import RpcHandler, RpcInternalError, RpcInvalidParamsError, method

from gateway.features.automation.application import AutomationService
from gateway.features.automation.presentation.mapping import (
    automation_response,
    automation_trigger,
    reminder_payload,
)
from gateway.features.automation.presentation.rpc import AutomationRpcMethod
from gateway.features.automation.presentation.schemas import (
    AutomationResponse,
    CreateAutomationParams,
    DeleteAutomationParams,
    DeleteAutomationResponse,
    GetAutomationParams,
    ListAutomationsParams,
    ListAutomationsResponse,
    UpdateAutomationParams,
)
from gateway.presentation.rpc import ResourceNotFoundError


class AutomationRpcMethods(RpcHandler):
    def __init__(self, service: AutomationService) -> None:
        self._service = service

    @method(
        AutomationRpcMethod.LIST,
        errors=(RpcInternalError,),
    )
    async def list_automations(
        self,
        params: ListAutomationsParams,
    ) -> ListAutomationsResponse:
        """List automations belonging to a conversation session."""
        jobs = await self._service.list_for_session(params.session_id)
        return ListAutomationsResponse(
            automations=tuple(automation_response(job) for job in jobs)
        )

    @method(
        AutomationRpcMethod.GET,
        errors=(ResourceNotFoundError, RpcInternalError),
    )
    async def get_automation(
        self,
        params: GetAutomationParams,
    ) -> AutomationResponse:
        job = await self._service.get_for_session(
            params.automation_id,
            params.session_id,
        )
        return automation_response(job)

    @method(
        AutomationRpcMethod.CREATE,
        errors=(RpcInvalidParamsError, RpcInternalError),
    )
    async def create_automation(
        self,
        params: CreateAutomationParams,
    ) -> AutomationResponse:
        job = await self._service.create_for_session(
            params.session_id,
            trigger=automation_trigger(params.schedule),
            payload=reminder_payload(params.payload),
            name=params.name,
        )
        return automation_response(job)

    @method(
        AutomationRpcMethod.UPDATE,
        errors=(ResourceNotFoundError, RpcInvalidParamsError, RpcInternalError),
    )
    async def update_automation(
        self,
        params: UpdateAutomationParams,
    ) -> AutomationResponse:
        job = await self._service.update_for_session(
            params.automation_id,
            params.session_id,
            trigger=automation_trigger(params.schedule),
            payload=reminder_payload(params.payload),
            name=params.name,
        )
        return automation_response(job)

    @method(
        AutomationRpcMethod.DELETE,
        errors=(ResourceNotFoundError, RpcInternalError),
    )
    async def delete_automation(
        self,
        params: DeleteAutomationParams,
    ) -> DeleteAutomationResponse:
        await self._service.delete_for_session(
            params.automation_id,
            params.session_id,
        )
        return DeleteAutomationResponse(deleted=params.automation_id)
