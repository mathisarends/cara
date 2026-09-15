from datetime import UTC, datetime, timedelta
from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import status
from fastapi_canon import CanonResponse, CanonRouter

from gateway.features.alarm.application import AlarmService
from gateway.features.alarm.presentation.errors import (
    ALARM_ERRORS,
    ALARM_NOT_FOUND,
    ALARM_STATE_CONFLICT,
    INVALID_ALARM,
)
from gateway.features.alarm.presentation.mapper import (
    to_alarm_list_response,
    to_alarm_response,
    to_pre_wake_lead,
    to_recurrence,
    to_routine,
    to_target,
)
from gateway.features.alarm.presentation.schemas import (
    AlarmListResponse,
    AlarmResponse,
    CreateAlarmRequest,
    DismissAlarmResponse,
    SetAlarmEnabledRequest,
    SnoozeAlarmRequest,
    UpdateAlarmRequest,
)
from gateway.features.conversation.presentation import SESSION_NOT_FOUND

alarm_router = CanonRouter(
    prefix="/v1/owners/{owner_id}/alarms",
    tags=["alarms"],
    route_class=DishkaRoute,
    error_registry=ALARM_ERRORS,
)


@alarm_router.get(
    "",
    operation_id="list_alarms",
    response_model=AlarmListResponse,
    summary="List an owner's alarms",
)
async def list_alarms(
    owner_id: str,
    service: FromDishka[AlarmService],
) -> AlarmListResponse:
    alarms = await service.list(owner_id)
    return to_alarm_list_response(alarms, datetime.now(UTC))


@alarm_router.get(
    "/{alarm_id}",
    operation_id="get_alarm",
    response_model=AlarmResponse,
    summary="Get an alarm",
    raises=[ALARM_NOT_FOUND],
)
async def get_alarm(
    owner_id: str,
    alarm_id: UUID,
    service: FromDishka[AlarmService],
) -> AlarmResponse:
    alarm = await service.get(alarm_id, owner_id)
    return to_alarm_response(alarm, datetime.now(UTC))


@alarm_router.post(
    "",
    operation_id="create_alarm",
    response_model=AlarmResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an alarm",
    raises=[SESSION_NOT_FOUND, INVALID_ALARM],
)
async def create_alarm(
    owner_id: str,
    request: CreateAlarmRequest,
    service: FromDishka[AlarmService],
) -> AlarmResponse:
    alarm = await service.create(
        owner_id,
        target=to_target(request.target),
        recurrence=to_recurrence(request.recurrence),
        routine=to_routine(request.routine),
        pre_wake_lead=to_pre_wake_lead(request.pre_wake_minutes),
        name=request.name,
    )
    return to_alarm_response(alarm, datetime.now(UTC))


@alarm_router.put(
    "/{alarm_id}",
    operation_id="update_alarm",
    response_model=AlarmResponse,
    summary="Replace an alarm's recurrence, routine, and pre-wake lead",
    raises=[ALARM_NOT_FOUND, INVALID_ALARM],
)
async def update_alarm(
    owner_id: str,
    alarm_id: UUID,
    request: UpdateAlarmRequest,
    service: FromDishka[AlarmService],
) -> AlarmResponse:
    alarm = await service.update(
        alarm_id,
        owner_id,
        recurrence=to_recurrence(request.recurrence),
        routine=to_routine(request.routine),
        pre_wake_lead=to_pre_wake_lead(request.pre_wake_minutes),
        name=request.name,
    )
    return to_alarm_response(alarm, datetime.now(UTC))


@alarm_router.delete(
    "/{alarm_id}",
    operation_id="delete_alarm",
    summary="Delete an alarm",
    raises=[ALARM_NOT_FOUND],
    response=CanonResponse.empty(description="The alarm was deleted."),
)
async def delete_alarm(
    owner_id: str,
    alarm_id: UUID,
    service: FromDishka[AlarmService],
) -> None:
    await service.delete(alarm_id, owner_id)


@alarm_router.put(
    "/{alarm_id}/enabled",
    operation_id="set_alarm_enabled",
    response_model=AlarmResponse,
    summary="Enable or disable an alarm",
    raises=[ALARM_NOT_FOUND, INVALID_ALARM],
)
async def set_alarm_enabled(
    owner_id: str,
    alarm_id: UUID,
    request: SetAlarmEnabledRequest,
    service: FromDishka[AlarmService],
) -> AlarmResponse:
    alarm = await service.set_enabled(alarm_id, owner_id, request.enabled)
    return to_alarm_response(alarm, datetime.now(UTC))


@alarm_router.post(
    "/{alarm_id}/skip-next",
    operation_id="skip_next_alarm",
    response_model=AlarmResponse,
    summary="Skip the next occurrence of a recurring alarm",
    raises=[ALARM_NOT_FOUND, ALARM_STATE_CONFLICT],
)
async def skip_next_alarm(
    owner_id: str,
    alarm_id: UUID,
    service: FromDishka[AlarmService],
) -> AlarmResponse:
    alarm = await service.skip_next(alarm_id, owner_id)
    return to_alarm_response(alarm, datetime.now(UTC))


@alarm_router.post(
    "/{alarm_id}/snooze",
    operation_id="snooze_alarm",
    response_model=AlarmResponse,
    summary="Snooze a ringing alarm",
    raises=[ALARM_NOT_FOUND, ALARM_STATE_CONFLICT],
)
async def snooze_alarm(
    owner_id: str,
    alarm_id: UUID,
    request: SnoozeAlarmRequest,
    service: FromDishka[AlarmService],
) -> AlarmResponse:
    alarm = await service.snooze(
        alarm_id,
        owner_id,
        timedelta(minutes=request.minutes),
    )
    return to_alarm_response(alarm, datetime.now(UTC))


@alarm_router.post(
    "/{alarm_id}/dismiss",
    operation_id="dismiss_alarm",
    response_model=DismissAlarmResponse,
    summary="Dismiss the current occurrence of an alarm",
    raises=[ALARM_NOT_FOUND, ALARM_STATE_CONFLICT],
)
async def dismiss_alarm(
    owner_id: str,
    alarm_id: UUID,
    service: FromDishka[AlarmService],
) -> DismissAlarmResponse:
    alarm = await service.dismiss(alarm_id, owner_id)
    return DismissAlarmResponse(
        alarm=None if alarm is None else to_alarm_response(alarm, datetime.now(UTC))
    )
