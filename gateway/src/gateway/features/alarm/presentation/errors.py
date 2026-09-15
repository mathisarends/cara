from fastapi_canon import Error, ErrorRegistry

from gateway.features.alarm.domain import (
    AlarmNotFoundError,
    AlarmStateError,
    InvalidAlarmError,
)
from gateway.features.conversation.presentation import SESSION_NOT_FOUND

ALARM_NOT_FOUND = Error(
    AlarmNotFoundError,
    status=404,
    code="alarm_not_found",
    title="Alarm not found",
    detail=str,
)

ALARM_STATE_CONFLICT = Error(
    AlarmStateError,
    status=409,
    code="alarm_state_conflict",
    title="Alarm state conflict",
    detail=str,
)

INVALID_ALARM = Error(
    InvalidAlarmError,
    status=422,
    code="invalid_alarm",
    title="Invalid alarm",
    detail=str,
)

ALARM_ERRORS = ErrorRegistry(
    name="alarm",
    # Creating an alarm resolves its session target through conversation.
    errors=[ALARM_NOT_FOUND, ALARM_STATE_CONFLICT, INVALID_ALARM, SESSION_NOT_FOUND],
)
