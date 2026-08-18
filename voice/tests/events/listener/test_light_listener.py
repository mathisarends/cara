import asyncio
from unittest.mock import AsyncMock

from voice.events import AssistantTurnStarted
from voice.events.bus import EventBus
from voice.events.listener.light_listener import LightListener


def test_visualizes_the_start_of_an_assistant_turn(
    event_bus: EventBus,
    light_visualization: AsyncMock,
) -> None:
    LightListener(event_bus, light_visualization)

    asyncio.run(event_bus.dispatch(AssistantTurnStarted()))

    light_visualization.show_agent_turn_started.assert_awaited_once_with()
