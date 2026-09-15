from dataclasses import dataclass

from gateway.features.alarm.domain.errors import InvalidAlarmError


@dataclass(frozen=True, slots=True)
class AlarmRoutine:
    skill: str
    note: str | None = None

    def __post_init__(self) -> None:
        if not self.skill.strip():
            raise InvalidAlarmError("Alarm routine skill must not be empty")
