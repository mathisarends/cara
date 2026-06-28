"""Philips Hue lifecycle listener.

Drives a Hue room's lighting in response to the assistant lifecycle so the room
visibly reflects what Cara is doing: listening, thinking, speaking, idle.

Credentials are read from the ``HUE_BRIDGE_IP`` and ``HUE_APP_KEY`` environment
variables (see :class:`hueify.Hueify`).
"""

from __future__ import annotations

import logging

from hueify import Color, Hueify
from hueify.grouped_lights import GroupedLights

from cara.events import EventBus
from cara.lifecycle import (
    AssistantState,
    SessionStarted,
    StateChanged,
)

logger = logging.getLogger(__name__)


# Maps each assistant phase to a (color, brightness%) light effect.
DEFAULT_STATE_EFFECTS: dict[AssistantState, tuple[Color, int]] = {
    AssistantState.LISTENING: (Color.OCEAN, 85),
    AssistantState.WAITING_FOLLOW_UP: (Color.TEAL, 55),
    AssistantState.TRANSCRIBING: (Color.CYAN, 75),
    AssistantState.THINKING: (Color.PURPLE, 60),
    AssistantState.SPEAKING: (Color.WARM_WHITE, 95),
    AssistantState.IDLE: (Color.WARM_WHITE, 50),
}


class HueLifecycleListener:
    """Reflects the assistant lifecycle on a Hue room's lights.

    Construct it, then ``await start()`` once (connects to the bridge and
    resolves the room) before subscribing it to the assistant event bus. Each
    ``StateChanged`` event sets the room's color and brightness; the room is
    switched on when a session begins.
    """

    def __init__(
        self,
        event_bus: EventBus,
        room_name: str = "Zimmer 1",
        *,
        hue: Hueify | None = None,
        state_effects: dict[AssistantState, tuple[Color, int]] | None = None,
    ) -> None:
        self._room_name = room_name
        self._hue = hue or Hueify()
        self._state_effects = state_effects or DEFAULT_STATE_EFFECTS
        self._room: GroupedLights | None = None
        event_bus.subscribe(SessionStarted, self.on_session_started)
        event_bus.subscribe(StateChanged, self.on_state_changed)

    async def start(self) -> None:
        """Connect to the bridge and resolve the target room. Call once."""
        await self._hue.connect()
        self._room = self._hue.rooms.from_name(self._room_name)
        logger.info("Hue listener bound to room %r", self._room_name)

    async def aclose(self) -> None:
        """Disconnect from the bridge. Safe to call multiple times."""
        await self._hue.close()

    async def on_session_started(self, event: SessionStarted) -> None:
        await self._turn_on()

    async def on_state_changed(self, event: StateChanged) -> None:
        await self._apply(event.state)

    async def _turn_on(self) -> None:
        if self._room is None:
            return
        await self._room.turn_on()

    async def _apply(self, state: AssistantState) -> None:
        if self._room is None:
            return
        effect = self._state_effects.get(state)
        if effect is None:
            return
        color, brightness = effect
        await self._room.set_named_color(color)
        await self._room.set_brightness(brightness)
