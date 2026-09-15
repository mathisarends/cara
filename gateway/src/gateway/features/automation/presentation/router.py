from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import Depends, status
from fastapi_canon import CanonResponse, CanonRouter

from gateway.features.automation.application import AutomationService
from gateway.features.automation.presentation.errors import (
    AUTOMATION_ERRORS,
    AUTOMATION_NOT_FOUND,
)
from gateway.features.automation.presentation.mapper import (
    to_action,
    to_automation_list_response,
    to_automation_response,
    to_schedule,
    to_target,
)
from gateway.features.automation.presentation.schemas import (
    AutomationListResponse,
    AutomationResponse,
    CreateAutomationRequest,
    UpdateAutomationRequest,
)
from gateway.features.conversation.presentation import SESSION_NOT_FOUND
from gateway.presentation.authentication import require_token

automation_router = CanonRouter(
    prefix="/v1/owners/{owner_id}/automations",
    tags=["automations"],
    route_class=DishkaRoute,
    error_registry=AUTOMATION_ERRORS,
    dependencies=[Depends(require_token)],
)


@automation_router.get(
    "",
    operation_id="list_automations",
    response_model=AutomationListResponse,
    summary="List an owner's automations",
)
async def list_automations(
    owner_id: str,
    service: FromDishka[AutomationService],
) -> AutomationListResponse:
    automations = await service.list(owner_id)
    return to_automation_list_response(automations)


@automation_router.get(
    "/{automation_id}",
    operation_id="get_automation",
    response_model=AutomationResponse,
    summary="Get an automation",
    raises=[AUTOMATION_NOT_FOUND],
)
async def get_automation(
    owner_id: str,
    automation_id: UUID,
    service: FromDishka[AutomationService],
) -> AutomationResponse:
    automation = await service.get(automation_id, owner_id)
    return to_automation_response(automation)


@automation_router.post(
    "",
    operation_id="create_automation",
    response_model=AutomationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an automation",
    raises=[SESSION_NOT_FOUND],
)
async def create_automation(
    owner_id: str,
    request: CreateAutomationRequest,
    service: FromDishka[AutomationService],
) -> AutomationResponse:
    automation = await service.create(
        owner_id,
        target=to_target(request.target),
        schedule=to_schedule(request.schedule),
        action=to_action(request.payload),
        name=request.name,
    )
    return to_automation_response(automation)


@automation_router.put(
    "/{automation_id}",
    operation_id="update_automation",
    response_model=AutomationResponse,
    summary="Replace an automation's schedule and payload",
    raises=[AUTOMATION_NOT_FOUND],
)
async def update_automation(
    owner_id: str,
    automation_id: UUID,
    request: UpdateAutomationRequest,
    service: FromDishka[AutomationService],
) -> AutomationResponse:
    automation = await service.update(
        automation_id,
        owner_id,
        schedule=to_schedule(request.schedule),
        action=to_action(request.payload),
        name=request.name,
    )
    return to_automation_response(automation)


@automation_router.delete(
    "/{automation_id}",
    operation_id="delete_automation",
    summary="Delete an automation",
    raises=[AUTOMATION_NOT_FOUND],
    response=CanonResponse.empty(description="The automation was deleted."),
)
async def delete_automation(
    owner_id: str,
    automation_id: UUID,
    service: FromDishka[AutomationService],
) -> None:
    await service.delete(automation_id, owner_id)
