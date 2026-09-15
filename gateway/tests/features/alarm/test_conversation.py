from datetime import timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from features.alarm.fakes import NEXT_WAKE, make_alarm, once_at
from gateway.features.alarm.domain import Alarm, DueRun
from gateway.features.alarm.infrastructure.conversation import (
    ConversationAlarmRunExecutor,
    _alarm_prompt,
)

_BERLIN = ZoneInfo("Europe/Berlin")


class _RecordingTurns:
    def __init__(self) -> None:
        self.started: list[tuple[UUID, str, dict[str, object]]] = []

    async def start_scheduled(
        self,
        *,
        session_id: UUID,
        text: str,
        metadata: dict[str, object],
    ) -> None:
        self.started.append((session_id, text, metadata))


def test_the_pre_wake_prompt_names_the_phase_wake_time_and_remaining_minutes() -> None:
    alarm = make_alarm(note="ohne Musik", name="Werktags")
    run = _run(alarm, NEXT_WAKE - timedelta(minutes=30))

    prompt = _alarm_prompt(alarm, run, run.due_at, _BERLIN)

    assert "Alarm: Werktags" in prompt
    assert "Phase: pre_wake" in prompt
    assert "Wake time: 2026-09-16 06:00 (Wednesday, Europe/Berlin)" in prompt
    assert "Current local time: 2026-09-16 05:30" in prompt
    assert "Minutes until wake time: 30" in prompt
    assert "Routine note: ohne Musik" in prompt
    assert 'Load the skill "wake-up" now' in prompt
    assert "Snooze count" not in prompt


def test_the_snooze_end_prompt_counts_snoozes_without_remaining_minutes() -> None:
    alarm = make_alarm(recurrence=once_at(NEXT_WAKE), pre_wake_lead=None)
    alarm.start_run(_run(alarm, NEXT_WAKE), NEXT_WAKE)
    alarm.snooze(timedelta(minutes=9), NEXT_WAKE)
    alarm.start_run(_run(alarm, NEXT_WAKE), NEXT_WAKE + timedelta(minutes=9))
    alarm.snooze(timedelta(minutes=9), NEXT_WAKE + timedelta(minutes=9))
    snooze_end = _run(alarm, NEXT_WAKE)
    alarm.start_run(snooze_end, snooze_end.due_at)

    prompt = _alarm_prompt(alarm, snooze_end, snooze_end.due_at, _BERLIN)

    assert f"Alarm: {alarm.id}" in prompt
    assert "Phase: snooze_end" in prompt
    assert "Snooze count: 2" in prompt
    assert "Minutes until wake time" not in prompt
    assert "Routine note" not in prompt


async def test_the_executor_starts_a_scheduled_turn_with_alarm_metadata() -> None:
    turns = _RecordingTurns()
    alarm = make_alarm(pre_wake_lead=None)
    run = _run(alarm, NEXT_WAKE)

    await ConversationAlarmRunExecutor(turns, _BERLIN).execute(alarm, run, NEXT_WAKE)

    [(session_id, text, metadata)] = turns.started
    assert session_id == alarm.target.session_id
    assert text.startswith("[Scheduled alarm run]")
    assert metadata == {
        "origin": "alarm",
        "alarm_id": str(alarm.id),
        "alarm_phase": "wake",
        "wake_at": NEXT_WAKE.isoformat(),
        "scheduled_for": NEXT_WAKE.isoformat(),
    }


def _run(alarm: Alarm, now) -> DueRun:
    run = alarm.next_due_run(now)
    assert run is not None
    return run
