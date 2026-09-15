from uuid import UUID


class AlarmNotFoundError(Exception):
    def __init__(self, alarm_id: UUID) -> None:
        super().__init__(f"Alarm {alarm_id} not found")


class AlarmStateError(Exception):
    pass


class InvalidAlarmError(ValueError):
    pass
