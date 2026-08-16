from typing import Protocol

from transitbus import EventBus

from agent.events import AssistantInterrupted, AssistantTurnStarted


class LightVisualization(Protocol):
    async def show_agent_turn_started(self) -> None: ...

    async def show_interruption(self) -> None: ...


class LightListener:
    """Visualizes agent activity and interruptions using light signals."""

    def __init__(self, event_bus: EventBus, visualization: LightVisualization) -> None:
        self._visualization = visualization

        event_bus.on(AssistantTurnStarted, self._on_agent_turn_started)
        event_bus.on(AssistantInterrupted, self._on_interrupted)

    async def _on_agent_turn_started(self, event: AssistantTurnStarted) -> None:
        await self._visualization.show_agent_turn_started()

    async def _on_interrupted(self, event: AssistantInterrupted) -> None:
        await self._visualization.show_interruption()
