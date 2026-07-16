"""Philips Hue listener.

Drives a Hue room's lighting in response to the assistant lifecycle so the room
visibly reflects what Cara is doing: listening, thinking, speaking, idle.

Credentials are read from the ``HUE_BRIDGE_IP`` and ``HUE_APP_KEY`` environment
variables (see :class:`hueify.Hueify`).
"""

import logging

from hueify import Color, Hueify
from hueify.grouped_lights import GroupedLights

from cara.events import (
    AssistantState,
    EventBus,
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
    AssistantState.CALLING_TOOL: (Color.VIOLET, 70),
    AssistantState.SPEAKING: (Color.WARM_WHITE, 95),
    AssistantState.IDLE: (Color.WARM_WHITE, 50),
}


class HueListener:
    """Reflects the assistant lifecycle on a Hue room's lights.

    Construct it with the assistant's event bus and it subscribes itself to the
    relevant events. The bridge connection is established lazily on the first
    event, so no explicit lifecycle management is required: each
    ``StateChanged`` event sets the room's color and brightness, and the room is
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
        self._event_bus = event_bus
        self._room_name = room_name
        self._hue = hue or Hueify()
        self._state_effects = state_effects or DEFAULT_STATE_EFFECTS
        self._room: GroupedLights | None = None
        self._event_bus.subscribe(SessionStarted, self._on_session_started)
        self._event_bus.subscribe(StateChanged, self._on_state_changed)

    async def _on_session_started(self, event: SessionStarted) -> None:
        room = await self._ensure_room()
        await room.turn_on()

    async def _on_state_changed(self, event: StateChanged) -> None:
        effect = self._state_effects.get(event.state)
        if effect is None:
            return
        room = await self._ensure_room()
        color, brightness = effect
        await room.set_named_color(color)
        await room.set_brightness(brightness)

    async def _ensure_room(self) -> GroupedLights:
        """Connect to the bridge and resolve the target room on first use."""
        if self._room is None:
            await self._hue.connect()
            self._room = self._hue.rooms.from_name(self._room_name)
            logger.info("Hue listener bound to room %r", self._room_name)
        return self._room
