from datetime import UTC, datetime

import pytest

from agent.clock import LocalClock


def test_clock_converts_utc_to_configured_timezone() -> None:
    clock = LocalClock(
        "Europe/Berlin",
        clock=lambda: datetime(2026, 8, 30, 11, 40, tzinfo=UTC),
    )

    assert clock.now().isoformat() == "2026-08-30T13:40:00+02:00"
    assert clock.today().isoformat() == "2026-08-30"


def test_clock_rejects_naive_instants() -> None:
    clock = LocalClock(clock=lambda: datetime(2026, 8, 30, 11, 40))

    with pytest.raises(ValueError, match="timezone information"):
        clock.now()
