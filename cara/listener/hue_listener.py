"""Philips Hue listener.

Nudges a Hue room's existing lighting to reflect the assistant lifecycle instead
of overriding it: the room's state at session start is the baseline, each phase
applies a relative shift on top of it, and everything reverts to the baseline
once idle or the session ends. A room that's off is left untouched.

The baseline itself is kept in sync with the room's own Hue Bridge events, so a
manual change made outside this listener (e.g. via the Hue app) shifts the
baseline instead of being fought or silently reverted.

Credentials are read from the ``HUE_BRIDGE_IP`` and ``HUE_APP_KEY`` environment
variables (see :class:`hueify.Hueify`).
"""

import logging
from dataclasses import dataclass, replace

from hueify import Hueify
from hueify.grouped_lights import GroupedLights
from hueify.sse.views import GroupedLightEvent

from cara.events import (
    AssistantState,
    EventBus,
    SessionEnded,
    SessionStarted,
    StateChanged,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Tint:
    """A relative nudge, in percentage points, applied on top of the baseline.

    ``temperature_delta`` follows Hueify's convention: positive shifts toward
    cooler white, negative toward warmer.
    """

    brightness_delta: int
    temperature_delta: int


_ZERO_TINT = _Tint(brightness_delta=0, temperature_delta=0)

# Noticeable but not extreme shifts per phase.
_STATE_TINTS: dict[AssistantState, _Tint] = {
    AssistantState.LISTENING: _Tint(brightness_delta=+15, temperature_delta=-20),
    AssistantState.WAITING_FOLLOW_UP: _Tint(brightness_delta=+6, temperature_delta=-12),
    AssistantState.TRANSCRIBING: _Tint(brightness_delta=+10, temperature_delta=-18),
    AssistantState.THINKING: _Tint(brightness_delta=-12, temperature_delta=+22),
    AssistantState.CALLING_TOOL: _Tint(brightness_delta=-18, temperature_delta=+28),
    AssistantState.SPEAKING: _Tint(brightness_delta=+20, temperature_delta=-25),
}
# IDLE has no tint - it means "back to baseline", handled explicitly below.

_BRIGHTNESS_RANGE = (0, 100)
_TEMPERATURE_RANGE = (0, 100)

# Hue's mirek color-temperature scale, mirroring hueify's own Resource constants.
_MIREK_MIN = 153
_MIREK_MAX = 500


@dataclass(frozen=True)
class _Baseline:
    on: bool
    brightness: float
    temperature: int | None


class HueListener:
    """Nudges a Hue room's existing lighting to reflect the assistant lifecycle.

    Rather than driving the room to fixed colors, this captures the room's
    state at session start as a baseline and applies a relative shift on top
    of it per phase, restoring exactly that baseline once idle or the session
    ends. A room that's off stays off.
    """

    def __init__(
        self,
        event_bus: EventBus,
        room_name: str = "Zimmer 1",
        *,
        hue: Hueify | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._room_name = room_name
        self._hue = hue or Hueify()
        self._room: GroupedLights | None = None
        self._baseline: _Baseline | None = None
        self._active_tint = _ZERO_TINT
        self._event_bus.subscribe(SessionStarted, self._on_session_started)
        self._event_bus.subscribe(SessionEnded, self._on_session_ended)
        self._event_bus.subscribe(StateChanged, self._on_state_changed)
        self._hue.on(GroupedLightEvent, self._on_bridge_event)

    async def _on_session_started(self, event: SessionStarted) -> None:
        room = await self._ensure_room()
        self._active_tint = _ZERO_TINT
        self._baseline = _Baseline(
            on=room.is_on,
            brightness=room.brightness_percentage,
            temperature=_read_temperature(room),
        )

    async def _on_session_ended(self, event: SessionEnded) -> None:
        await self._restore_baseline()

    async def _on_state_changed(self, event: StateChanged) -> None:
        if event.state is AssistantState.IDLE:
            await self._restore_baseline()
            return

        tint = _STATE_TINTS.get(event.state)
        baseline = self._baseline
        if tint is None or baseline is None or not baseline.on:
            return

        self._active_tint = tint
        room = await self._ensure_room()
        await room.set_brightness(_clamp(baseline.brightness + tint.brightness_delta, *_BRIGHTNESS_RANGE))
        if baseline.temperature is not None:
            await room.set_color_temperature(_clamp(baseline.temperature + tint.temperature_delta, *_TEMPERATURE_RANGE))

    async def _restore_baseline(self) -> None:
        baseline = self._baseline
        self._active_tint = _ZERO_TINT
        if baseline is None or not baseline.on:
            return
        room = await self._ensure_room()
        await room.set_brightness(baseline.brightness)
        if baseline.temperature is not None:
            await room.set_color_temperature(baseline.temperature)

    async def _on_bridge_event(self, event: GroupedLightEvent) -> None:
        """Fold a Hue Bridge report for our room back into the baseline.

        Reported values are corrected by the currently applied tint before
        being adopted: our own commands echo back as a no-op, while a change
        made outside this listener shifts the baseline underneath the tint
        instead of being overwritten on the next restore.
        """
        baseline = self._baseline
        if baseline is None or self._room is None or event.id != self._room.id:
            return

        tint = self._active_tint
        if event.on is not None:
            baseline = replace(baseline, on=event.on.on)
        if event.dimming is not None:
            baseline = replace(
                baseline,
                brightness=_clamp(event.dimming.brightness - tint.brightness_delta, *_BRIGHTNESS_RANGE),
            )
        if event.color_temperature is not None and event.color_temperature.mirek is not None:
            reported = _mirek_to_percentage(event.color_temperature.mirek)
            baseline = replace(
                baseline,
                temperature=_clamp(reported - tint.temperature_delta, *_TEMPERATURE_RANGE),
            )
        self._baseline = baseline

    async def _ensure_room(self) -> GroupedLights:
        """Connect to the bridge and resolve the target room on first use."""
        if self._room is None:
            await self._hue.connect()
            self._room = self._hue.rooms.from_name(self._room_name)
            logger.info("Hue listener bound to room %r", self._room_name)
        return self._room


def _clamp(value: float, lo: int, hi: int) -> float:
    return max(lo, min(hi, value))


def _mirek_to_percentage(mirek: int) -> int:
    return int(((mirek - _MIREK_MIN) / (_MIREK_MAX - _MIREK_MIN)) * 100)


def _read_temperature(room: GroupedLights) -> int | None:
    """Hueify raises instead of returning None for a light in color mode whose
    color_temperature block still carries a null mirek value."""
    try:
        return room.color_temperature_percentage
    except TypeError:
        return None
