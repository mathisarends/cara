from datetime import UTC, datetime, timedelta

from pyrpckit import Inject, RpcInternalError, RpcInvalidParamsError, RpcModule

from gateway.features.alarm.application import AlarmService
from gateway.features.alarm.presentation.rpc.mapping import (
    alarm_recurrence,
    alarm_response,
    alarm_routine,
    alarm_target,
    pre_wake_lead,
)
from gateway.features.alarm.presentation.rpc.models import (
    AlarmResponse,
    AlarmRpcMethod,
    CreateAlarmParams,
    DeleteAlarmParams,
    DeleteAlarmResponse,
    DismissAlarmParams,
    DismissAlarmResponse,
    GetAlarmParams,
    ListAlarmsParams,
    ListAlarmsResponse,
    SetAlarmEnabledParams,
    SkipNextAlarmParams,
    SnoozeAlarmParams,
    UpdateAlarmParams,
)
from gateway.presentation.rpc.errors import ResourceNotFoundError

alarm_module = RpcModule()

_COMMAND_ERRORS = (ResourceNotFoundError, RpcInvalidParamsError, RpcInternalError)


@alarm_module.method(AlarmRpcMethod.LIST, errors=(RpcInternalError,))
async def list_alarms(
    params: ListAlarmsParams,
    service: Inject[AlarmService],
) -> ListAlarmsResponse:
    """List alarms belonging to an owner, across all of their targets."""
    alarms = await service.list(params.owner_id)
    now = datetime.now(UTC)
    return ListAlarmsResponse(
        alarms=tuple(alarm_response(item, now) for item in alarms)
    )


@alarm_module.method(
    AlarmRpcMethod.GET, errors=(ResourceNotFoundError, RpcInternalError)
)
async def get_alarm(
    params: GetAlarmParams,
    service: Inject[AlarmService],
) -> AlarmResponse:
    alarm = await service.get(params.alarm_id, params.owner_id)
    return alarm_response(alarm, datetime.now(UTC))


@alarm_module.method(AlarmRpcMethod.CREATE, errors=_COMMAND_ERRORS)
async def create_alarm(
    params: CreateAlarmParams,
    service: Inject[AlarmService],
) -> AlarmResponse:
    alarm = await service.create(
        params.owner_id,
        target=alarm_target(params.target),
        recurrence=alarm_recurrence(params.recurrence),
        routine=alarm_routine(params.routine),
        pre_wake_lead=pre_wake_lead(params.pre_wake_minutes),
        name=params.name,
    )
    return alarm_response(alarm, datetime.now(UTC))


@alarm_module.method(AlarmRpcMethod.UPDATE, errors=_COMMAND_ERRORS)
async def update_alarm(
    params: UpdateAlarmParams,
    service: Inject[AlarmService],
) -> AlarmResponse:
    """Replace an alarm's recurrence, routine, pre-wake lead, and name."""
    alarm = await service.update(
        params.alarm_id,
        params.owner_id,
        recurrence=alarm_recurrence(params.recurrence),
        routine=alarm_routine(params.routine),
        pre_wake_lead=pre_wake_lead(params.pre_wake_minutes),
        name=params.name,
    )
    return alarm_response(alarm, datetime.now(UTC))


@alarm_module.method(
    AlarmRpcMethod.DELETE, errors=(ResourceNotFoundError, RpcInternalError)
)
async def delete_alarm(
    params: DeleteAlarmParams,
    service: Inject[AlarmService],
) -> DeleteAlarmResponse:
    await service.delete(params.alarm_id, params.owner_id)
    return DeleteAlarmResponse(deleted=params.alarm_id)


@alarm_module.method(AlarmRpcMethod.SET_ENABLED, errors=_COMMAND_ERRORS)
async def set_alarm_enabled(
    params: SetAlarmEnabledParams,
    service: Inject[AlarmService],
) -> AlarmResponse:
    alarm = await service.set_enabled(params.alarm_id, params.owner_id, params.enabled)
    return alarm_response(alarm, datetime.now(UTC))


@alarm_module.method(AlarmRpcMethod.SKIP_NEXT, errors=_COMMAND_ERRORS)
async def skip_next_alarm(
    params: SkipNextAlarmParams,
    service: Inject[AlarmService],
) -> AlarmResponse:
    """Skip the next upcoming occurrence of a recurring alarm."""
    alarm = await service.skip_next(params.alarm_id, params.owner_id)
    return alarm_response(alarm, datetime.now(UTC))


@alarm_module.method(AlarmRpcMethod.SNOOZE, errors=_COMMAND_ERRORS)
async def snooze_alarm(
    params: SnoozeAlarmParams,
    service: Inject[AlarmService],
) -> AlarmResponse:
    alarm = await service.snooze(
        params.alarm_id,
        params.owner_id,
        timedelta(minutes=params.minutes),
    )
    return alarm_response(alarm, datetime.now(UTC))


@alarm_module.method(AlarmRpcMethod.DISMISS, errors=_COMMAND_ERRORS)
async def dismiss_alarm(
    params: DismissAlarmParams,
    service: Inject[AlarmService],
) -> DismissAlarmResponse:
    """Dismiss the current occurrence; a one-time alarm is removed."""
    alarm = await service.dismiss(params.alarm_id, params.owner_id)
    return DismissAlarmResponse(
        alarm=None if alarm is None else alarm_response(alarm, datetime.now(UTC))
    )
