from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

_WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
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


class RuntimeContext:
    """Ambient facts the assistant should always know: where it is and the local time now.

    Rendered fresh on every turn so the current time stays accurate.
    """

    def __init__(self, *, location_name: str, timezone: str, clock: Callable[[], datetime] | None = None) -> None:
        self._location_name = location_name
        self._timezone = timezone
        self._clock = clock or (lambda: datetime.now(ZoneInfo(timezone)))

    def render(self) -> str:
        now = self._clock()
        weekday = _WEEKDAYS[now.weekday()]
        month = _MONTHS[now.month - 1]
        stamp = f"{weekday}, {now.day}. {month} {now.year}, {now:%H:%M} Uhr"
        return f"Aktueller Standort: {self._location_name}\nAktuelle lokale Zeit: {stamp}"
