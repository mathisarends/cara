from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from features.alarm.fakes import NEXT_WAKE, NOW
from gateway.features.alarm.application import AlarmService
from gateway.features.alarm.domain import (
    AlarmStateError,
    InvalidAlarmError,
    OccurrenceState,
)
from gateway.features.alarm.presentation.rpc.methods import (
    create_alarm,
    delete_alarm,
    dismiss_alarm,
    get_alarm,
    list_alarms,
    set_alarm_enabled,
    skip_next_alarm,
    snooze_alarm,
    update_alarm,
)
from gateway.features.alarm.presentation.rpc.models import (
    AlarmRoutine,
    CreateAlarmParams,
    DeleteAlarmParams,
    DismissAlarmParams,
    GetAlarmParams,
    ListAlarmsParams,
    OnceAlarmRecurrence,
    SessionAlarmTarget,
    SetAlarmEnabledParams,
    SkipNextAlarmParams,
    SnoozeAlarmParams,
    UpdateAlarmParams,
    WeeklyAlarmRecurrence,
)

_OWNER = "owner"
_WEEKDAYS = WeeklyAlarmRecurrence(
    days=("mon", "tue", "wed", "thu", "fri"),
    local_time="06:00",
    timezone="Europe/Berlin",
)


async def test_create_list_get_and_delete_an_alarm(
    alarm_service: AlarmService,
) -> None:
    created = await create_alarm(
        CreateAlarmParams(
            owner_id=_OWNER,
            target=SessionAlarmTarget(session_id=uuid4()),
            recurrence=_WEEKDAYS,
            routine=AlarmRoutine(skill="wake-up"),
            pre_wake_minutes=30,
            name="Werktags",
        ),
        alarm_service,
    )
    listed = await list_alarms(ListAlarmsParams(owner_id=_OWNER), alarm_service)
    fetched = await get_alarm(
        GetAlarmParams(owner_id=_OWNER, alarm_id=created.id), alarm_service
    )

    assert listed.alarms == (created,)
    assert fetched == created
    assert fetched.recurrence == _WEEKDAYS
    assert fetched.pre_wake_minutes == 30
    assert fetched.enabled
    assert fetched.occurrence is not None
    assert fetched.occurrence.wake_at == NEXT_WAKE
    assert fetched.occurrence.state is OccurrenceState.UPCOMING

    deleted = await delete_alarm(
        DeleteAlarmParams(owner_id=_OWNER, alarm_id=created.id), alarm_service
    )
    assert deleted.deleted == created.id
    assert (
        await list_alarms(ListAlarmsParams(owner_id=_OWNER), alarm_service)
    ).alarms == ()


async def test_update_enable_and_skip_an_alarm(alarm_service: AlarmService) -> None:
    created = await _create(alarm_service)
    wake_at = NOW + timedelta(hours=8)

    updated = await update_alarm(
        UpdateAlarmParams(
            owner_id=_OWNER,
            alarm_id=created.id,
            recurrence=OnceAlarmRecurrence(wake_at=wake_at),
            routine=AlarmRoutine(skill="wake-up", note="ohne Musik"),
        ),
        alarm_service,
    )
    assert updated.recurrence == OnceAlarmRecurrence(wake_at=wake_at)
    assert updated.pre_wake_minutes is None
    assert updated.next_run is not None
    assert updated.next_run.due_at == wake_at

    disabled = await set_alarm_enabled(
        SetAlarmEnabledParams(owner_id=_OWNER, alarm_id=created.id, enabled=False),
        alarm_service,
    )
    assert disabled.occurrence is None
    assert disabled.next_run is None

    weekly = await _create(alarm_service)
    skipped = await skip_next_alarm(
        SkipNextAlarmParams(owner_id=_OWNER, alarm_id=weekly.id), alarm_service
    )
    assert skipped.skipped_dates == (NEXT_WAKE.date(),)


async def test_snooze_and_dismiss_reject_an_alarm_that_is_not_ringing(
    alarm_service: AlarmService,
) -> None:
    created = await _create(alarm_service)

    with pytest.raises(AlarmStateError):
        await snooze_alarm(
            SnoozeAlarmParams(owner_id=_OWNER, alarm_id=created.id, minutes=9),
            alarm_service,
        )
    with pytest.raises(AlarmStateError):
        await dismiss_alarm(
            DismissAlarmParams(owner_id=_OWNER, alarm_id=created.id), alarm_service
        )


async def test_a_one_time_alarm_in_the_past_is_invalid(
    alarm_service: AlarmService,
) -> None:
    with pytest.raises(InvalidAlarmError):
        await create_alarm(
            CreateAlarmParams(
                owner_id=_OWNER,
                target=SessionAlarmTarget(session_id=uuid4()),
                recurrence=OnceAlarmRecurrence(wake_at=NOW - timedelta(minutes=1)),
                routine=AlarmRoutine(skill="wake-up"),
            ),
            alarm_service,
        )


@pytest.mark.parametrize(
    "build",
    [
        lambda: WeeklyAlarmRecurrence(days=(), local_time="06:00", timezone="UTC"),
        lambda: WeeklyAlarmRecurrence(days=("mon",), local_time="6:00", timezone="UTC"),
        lambda: WeeklyAlarmRecurrence(
            days=("mon",), local_time="06:00", timezone="Mars"
        ),
        lambda: WeeklyAlarmRecurrence(
            days=("moon",), local_time="06:00", timezone="UTC"
        ),
        lambda: AlarmRoutine(skill=""),
        lambda: SnoozeAlarmParams(owner_id=_OWNER, alarm_id=uuid4(), minutes=0),
        lambda: SnoozeAlarmParams(owner_id=_OWNER, alarm_id=uuid4(), minutes=61),
        lambda: CreateAlarmParams(
            owner_id=_OWNER,
            target=SessionAlarmTarget(session_id=uuid4()),
            recurrence=_WEEKDAYS,
            routine=AlarmRoutine(skill="wake-up"),
            pre_wake_minutes=121,
        ),
        lambda: CreateAlarmParams(
            owner_id=_OWNER,
            target=SessionAlarmTarget(session_id=uuid4()),
            recurrence=_WEEKDAYS,
            routine=AlarmRoutine(skill="wake-up"),
            pre_wake_minutes=0,
        ),
    ],
)
def test_rejects_invalid_params(build) -> None:
    with pytest.raises(ValidationError):
        build()


async def _create(service: AlarmService):
    return await create_alarm(
        CreateAlarmParams(
            owner_id=_OWNER,
            target=SessionAlarmTarget(session_id=uuid4()),
            recurrence=_WEEKDAYS.model_copy(
                update={"days": ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}
            ),
            routine=AlarmRoutine(skill="wake-up"),
        ),
        service,
    )
