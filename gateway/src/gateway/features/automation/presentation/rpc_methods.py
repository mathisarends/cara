from gateway.features.automation.application import AutomationService
from gateway.features.automation.presentation.mapping import automation_response
from gateway.features.automation.presentation.rpc import AutomationRpcMethod
from gateway.features.automation.presentation.schemas import (
    AutomationResponse,
    GetAutomationParams,
    ListAutomationsParams,
    ListAutomationsResponse,
)
from gateway.presentation import rpc
from gateway.presentation.rpc import RpcErrorCode


class AutomationRpcMethods(rpc.RpcHandler):
    def __init__(self, service: AutomationService) -> None:
        self._service = service

    @rpc.method(
        AutomationRpcMethod.LIST,
        errors=(RpcErrorCode.INTERNAL_ERROR,),
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

    @rpc.method(
        AutomationRpcMethod.GET,
        summary="Get an automation belonging to a conversation session.",
        errors=(RpcErrorCode.RESOURCE_NOT_FOUND, RpcErrorCode.INTERNAL_ERROR),
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
