import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from gateway.features.alarm.application import AlarmRunExecutor, AlarmTargetResolver
from gateway.features.alarm.domain import (
    Alarm,
    AlarmPhase,
    AlarmTarget,
    DueRun,
    OnceRecurrence,
    SessionTarget,
    WeeklyRecurrence,
)
from gateway.features.conversation.application import SessionService, TurnService

logger = logging.getLogger(__name__)


class ConversationAlarmTargetResolver(AlarmTargetResolver):
    def __init__(self, sessions: SessionService) -> None:
        self._sessions = sessions

    async def require(self, target: AlarmTarget) -> None:
        match target:
            case SessionTarget(session_id=session_id):
                await self._sessions.get(session_id)


class ConversationAlarmRunExecutor(AlarmRunExecutor):
    def __init__(self, turns: TurnService, local_timezone: ZoneInfo) -> None:
        self._turns = turns
        self._local_timezone = local_timezone

    async def execute(self, alarm: Alarm, run: DueRun, now: datetime) -> None:
        metadata: dict[str, object] = {
            "origin": "alarm",
            "alarm_id": str(alarm.id),
            "alarm_phase": str(run.phase),
            "wake_at": run.wake_at.isoformat(),
            "scheduled_for": run.due_at.isoformat(),
        }
        logger.info("Running %s phase of alarm %s", run.phase, alarm.id)
        match alarm.target:
            case SessionTarget(session_id=session_id):
                await self._turns.start_scheduled(
                    session_id=session_id,
                    text=_alarm_prompt(alarm, run, now, self._local_timezone),
                    metadata=metadata,
                )


def _alarm_prompt(
    alarm: Alarm,
    run: DueRun,
    now: datetime,
    local_timezone: ZoneInfo,
) -> str:
    zone = _zone(alarm, local_timezone)
    wake_at = run.wake_at.astimezone(zone)
    lines = [
        "[Scheduled alarm run]",
        f"Alarm: {alarm.name or alarm.id}",
        f"Phase: {run.phase}",
        f"Wake time: {wake_at:%Y-%m-%d %H:%M} ({wake_at:%A}, {zone.key})",
        f"Current local time: {now.astimezone(zone):%Y-%m-%d %H:%M}",
    ]
    if run.phase is AlarmPhase.PRE_WAKE:
        minutes = max(0, round((run.wake_at - now).total_seconds() / 60))
        lines.append(f"Minutes until wake time: {minutes}")
    if run.phase is AlarmPhase.SNOOZE_END and alarm.occurrence is not None:
        lines.append(f"Snooze count: {alarm.occurrence.snooze_count}")
    if alarm.routine.note:
        lines.append(f"Routine note: {alarm.routine.note}")
    lines.extend(
        (
            f'Load the skill "{alarm.routine.skill}" now and carry out its '
            "instructions for this phase. The routine note, if present, takes "
            "precedence over the skill defaults.",
            "Start long-running effects (such as a sunrise or music) so that they "
            "continue on their devices, and return without waiting for them to finish.",
            "Do not create, update, snooze, skip or dismiss alarms in this run.",
        )
    )
    return "\n".join(lines)


def _zone(alarm: Alarm, local_timezone: ZoneInfo) -> ZoneInfo:
    match alarm.recurrence:
        case WeeklyRecurrence(timezone=timezone):
            return ZoneInfo(timezone)
        case OnceRecurrence():
            return local_timezone
