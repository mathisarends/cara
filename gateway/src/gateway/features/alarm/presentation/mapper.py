from collections.abc import Iterable
from datetime import datetime, time, timedelta

from gateway.features.alarm import domain
from gateway.features.alarm.presentation.schemas import (
    AlarmListResponse,
    AlarmNextRun,
    AlarmOccurrence,
    AlarmRecurrence,
    AlarmResponse,
    AlarmRoutine,
    AlarmTarget,
    OnceAlarmRecurrence,
    SessionAlarmTarget,
    WeeklyAlarmRecurrence,
)


def to_alarm_list_response(
    alarms: Iterable[domain.Alarm],
    now: datetime,
) -> AlarmListResponse:
    return AlarmListResponse(
        alarms=tuple(to_alarm_response(item, now) for item in alarms)
    )


def to_alarm_response(alarm: domain.Alarm, now: datetime) -> AlarmResponse:
    next_run = alarm.next_due_run(now)
    occurrence = alarm.occurrence
    lead = alarm.pre_wake_lead
    return AlarmResponse(
        id=alarm.id,
        owner_id=alarm.owner_id,
        name=alarm.name,
        created_at=alarm.created_at,
        enabled=alarm.enabled,
        target=_to_target_schema(alarm.target),
        recurrence=_to_recurrence_schema(alarm.recurrence),
        routine=AlarmRoutine(skill=alarm.routine.skill, note=alarm.routine.note),
        pre_wake_minutes=None if lead is None else int(lead.total_seconds() // 60),
        skipped_dates=tuple(sorted(alarm.skipped_dates)),
        occurrence=(
            None
            if occurrence is None
            else AlarmOccurrence(
                wake_at=occurrence.wake_at,
                state=occurrence.state,
                snooze_count=occurrence.snooze_count,
                snoozed_until=occurrence.snoozed_until,
            )
        ),
        next_run=(
            None
            if next_run is None
            else AlarmNextRun(phase=next_run.phase, due_at=next_run.due_at)
        ),
    )


def to_recurrence(recurrence: AlarmRecurrence) -> domain.AlarmRecurrence:
    match recurrence:
        case OnceAlarmRecurrence(wake_at=wake_at):
            return domain.OnceRecurrence(wake_at=wake_at)
        case WeeklyAlarmRecurrence(days=days, local_time=local_time, timezone=timezone):
            return domain.WeeklyRecurrence(
                days=frozenset(days),
                local_time=time.fromisoformat(local_time),
                timezone=timezone,
            )


def to_target(target: AlarmTarget) -> domain.AlarmTarget:
    match target:
        case SessionAlarmTarget(session_id=session_id):
            return domain.SessionTarget(session_id)


def to_routine(routine: AlarmRoutine) -> domain.AlarmRoutine:
    return domain.AlarmRoutine(skill=routine.skill, note=routine.note)


def to_pre_wake_lead(minutes: int | None) -> timedelta | None:
    return None if minutes is None else timedelta(minutes=minutes)


def _to_recurrence_schema(recurrence: domain.AlarmRecurrence) -> AlarmRecurrence:
    match recurrence:
        case domain.OnceRecurrence(wake_at=wake_at):
            return OnceAlarmRecurrence(wake_at=wake_at)
        case domain.WeeklyRecurrence(
            days=days,
            local_time=local_time,
            timezone=timezone,
        ):
            return WeeklyAlarmRecurrence(
                days=tuple(day for day in domain.Weekday if day in days),
                local_time=f"{local_time:%H:%M}",
                timezone=timezone,
            )


def _to_target_schema(target: domain.AlarmTarget) -> AlarmTarget:
    match target:
        case domain.SessionTarget(session_id=session_id):
            return SessionAlarmTarget(session_id=session_id)
