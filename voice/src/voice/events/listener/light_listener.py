from typing import Protocol

from voice.events import AssistantTurnStarted
from voice.events.bus import EventBus


class LightVisualization(Protocol):
    async def show_agent_turn_started(self) -> None: ...


class LightListener:
    """Visualizes agent activity using light signals."""

    def __init__(self, event_bus: EventBus, visualization: LightVisualization) -> None:
        self._visualization = visualization

        event_bus.on(AssistantTurnStarted, self._on_agent_turn_started)

    async def _on_agent_turn_started(self, event: AssistantTurnStarted) -> None:
        await self._visualization.show_agent_turn_started()
