import asyncio
from datetime import UTC, datetime

from agent.clock import LocalClock
from agent.tools.factory import _create_tools


def test_current_time_returns_configured_local_time(make_tool_context) -> None:
    clock = LocalClock(
        "Europe/Berlin",
        clock=lambda: datetime(2026, 8, 30, 11, 40, tzinfo=UTC),
    )
    tools = _create_tools(make_tool_context(clock=clock))

    result = asyncio.run(tools.execute("current_time", {}))

    assert result == (
        "Current local date and time: 2026-08-30T13:40:00+02:00 (Europe/Berlin, CEST)."
    )
