from collections.abc import Callable
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "Europe/Berlin"


class LocalClock:
    """Provide the current date and time in the configured local timezone."""

    def __init__(
        self,
        timezone: str = DEFAULT_TIMEZONE,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._timezone = ZoneInfo(timezone)
        self._clock = clock or (lambda: datetime.now(UTC))

    @property
    def timezone(self) -> str:
        return self._timezone.key

    def now(self) -> datetime:
        instant = self._clock()
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("Clock values must include timezone information")
        return instant.astimezone(self._timezone)

    def today(self) -> date:
        return self.now().date()
