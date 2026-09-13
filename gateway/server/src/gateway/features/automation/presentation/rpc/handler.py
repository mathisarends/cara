from gateway.features.automation.application import SessionAutomationService
from gateway.features.automation.presentation.rpc.mapping import (
    automation_origin,
    automation_response,
    automation_schedule,
    prompt_action,
)
from gateway.features.automation.presentation.rpc.schemas import (
    AutomationResponse,
    CreateAutomationParams,
    DeleteAutomationParams,
    DeleteAutomationResponse,
    GetAutomationParams,
    ListAutomationsParams,
    ListAutomationsResponse,
    UpdateAutomationParams,
)


class AutomationRpcMethods:
    def __init__(self, service: SessionAutomationService) -> None:
        self._service = service

    async def list_automations(
        self,
        params: ListAutomationsParams,
    ) -> ListAutomationsResponse:
        """List automations belonging to a conversation session."""
        automations = await self._service.list(params.session_id)
        return ListAutomationsResponse(
            automations=tuple(automation_response(item) for item in automations)
        )

    async def get_automation(
        self,
        params: GetAutomationParams,
    ) -> AutomationResponse:
        automation = await self._service.get(
            params.automation_id,
            params.session_id,
        )
        return automation_response(automation)

    async def create_automation(
        self,
        params: CreateAutomationParams,
    ) -> AutomationResponse:
        automation = await self._service.create(
            params.session_id,
            schedule=automation_schedule(params.schedule),
            action=prompt_action(params.payload),
            origin=automation_origin(params.payload),
            name=params.name,
        )
        return automation_response(automation)

    async def update_automation(
        self,
        params: UpdateAutomationParams,
    ) -> AutomationResponse:
        automation = await self._service.update(
            params.automation_id,
            params.session_id,
            schedule=automation_schedule(params.schedule),
            action=prompt_action(params.payload),
            origin=automation_origin(params.payload),
            name=params.name,
        )
        return automation_response(automation)

    async def delete_automation(
        self,
        params: DeleteAutomationParams,
    ) -> DeleteAutomationResponse:
        await self._service.delete(params.automation_id, params.session_id)
        return DeleteAutomationResponse(deleted=params.automation_id)
