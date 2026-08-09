from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

_WEEKDAYS = (
    "Montag",
    "Dienstag",
    "Mittwoch",
    "Donnerstag",
    "Freitag",
    "Samstag",
    "Sonntag",
)
_MONTHS = (
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
)


class LocalTimePrompt:
    """Render the current local weekday, date, and time for the system prompt."""

    def __init__(
        self, *, timezone: str, clock: Callable[[], datetime] | None = None
    ) -> None:
        self._clock = clock or (lambda: datetime.now(ZoneInfo(timezone)))

    def render(self) -> str:
        now = self._clock()
        weekday = _WEEKDAYS[now.weekday()]
        month = _MONTHS[now.month - 1]
        stamp = f"{weekday}, {now.day}. {month} {now.year}, {now:%H:%M} Uhr"
        return stamp
