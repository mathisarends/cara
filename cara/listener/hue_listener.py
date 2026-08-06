import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace

from hueify import Hueify
from hueify.grouped_lights import GroupedLights
from hueify.sse.views import GroupedLightEvent
from transitbus import EventBus

from cara.events import (
    AssistantTurnStarted,
    SessionEnded,
    SessionStarted,
    ToolCallFinished,
    ToolCallStarted,
    UserTurnStarted,
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
_USER_TINT = _Tint(brightness_delta=+15, temperature_delta=-20)
_ASSISTANT_TINT = _Tint(brightness_delta=-12, temperature_delta=+22)
_TOOL_PROGRESS_TINTS = (
    _Tint(brightness_delta=-18, temperature_delta=+28),
    _Tint(brightness_delta=-6, temperature_delta=+28),
)

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
    """Nudges a Hue room's lighting to reflect the conversation lifecycle.

    Rather than driving the room to fixed colors, this captures the room's
    state at session start as a baseline and applies a relative shift while the
    user, model, or a tool is active. It restores that baseline when the session
    ends. A room that's off stays off.

    Every Hue API call runs on a single background worker fed by an internal
    queue, so the event handlers only enqueue and return: bridge I/O never
    adds latency to the agentic loop that dispatches the events. Serializing
    the work through one worker also keeps successive lifecycle phases from
    interleaving their awaits on the shared baseline and room.
    """

    def __init__(
        self,
        event_bus: EventBus,
        room_name: str = "Mein Zimmer",
        *,
        hue: Hueify | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._room_name = room_name
        self._hue = hue or Hueify()
        self._room: GroupedLights | None = None
        self._hue_open = False
        self._baseline: _Baseline | None = None
        self._active_tint = _ZERO_TINT
        self._tool_progress_index = 0
        self._active_tool_calls = 0
        self._jobs: asyncio.Queue[Callable[[], Awaitable[None]]] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None
        self._event_bus.on(SessionStarted, self._on_session_started)
        self._event_bus.on(SessionEnded, self._on_session_ended)
        self._event_bus.on(UserTurnStarted, self._on_user_turn_started)
        self._event_bus.on(AssistantTurnStarted, self._on_assistant_turn_started)
        self._event_bus.on(ToolCallStarted, self._on_tool_call_started)
        self._event_bus.on(ToolCallFinished, self._on_tool_call_finished)
        self._hue.on(GroupedLightEvent, self._on_bridge_event)

    async def _on_session_started(self, event: SessionStarted) -> None:
        self._submit(self._capture_baseline)

    async def _on_session_ended(self, event: SessionEnded) -> None:
        self._submit(self._restore_baseline)

    async def _on_user_turn_started(self, event: UserTurnStarted) -> None:
        self._submit(self._apply_user_tint)

    async def _on_assistant_turn_started(self, event: AssistantTurnStarted) -> None:
        self._submit(self._apply_assistant_tint)

    async def _on_tool_call_started(self, event: ToolCallStarted) -> None:
        self._active_tool_calls += 1
        self._submit(self._apply_tool_progress_signal)

    async def _on_tool_call_finished(self, event: ToolCallFinished) -> None:
        self._active_tool_calls = max(0, self._active_tool_calls - 1)
        if self._active_tool_calls == 0:
            self._submit(self._apply_assistant_tint)

    def _submit(self, job: Callable[[], Awaitable[None]]) -> None:
        """Enqueue a Hue operation for the background worker and return at once."""
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run())
        self._jobs.put_nowait(job)

    async def _run(self) -> None:
        while True:
            job = await self._jobs.get()
            try:
                await job()
            except Exception:
                logger.exception("Hue operation failed")
            finally:
                self._jobs.task_done()

    async def _capture_baseline(self) -> None:
        room = await self._ensure_room()
        self._active_tint = _ZERO_TINT
        self._tool_progress_index = 0
        self._active_tool_calls = 0
        self._baseline = _Baseline(
            on=room.is_on,
            brightness=room.brightness_percentage,
            temperature=_read_temperature(room),
        )

    async def _apply_user_tint(self) -> None:
        await self._apply_tint(_USER_TINT)

    async def _apply_assistant_tint(self) -> None:
        await self._apply_tint(_ASSISTANT_TINT)

    async def _apply_tool_progress_signal(self) -> None:
        tint = _TOOL_PROGRESS_TINTS[self._tool_progress_index % len(_TOOL_PROGRESS_TINTS)]
        self._tool_progress_index += 1
        await self._apply_tint(tint)

    async def _apply_tint(self, tint: _Tint) -> None:
        baseline = self._baseline
        if baseline is None or not baseline.on:
            return

        self._active_tint = tint
        room = await self._ensure_room()
        await room.set_brightness(_clamp(baseline.brightness + tint.brightness_delta, *_BRIGHTNESS_RANGE))
        if baseline.temperature is not None:
            await room.set_color_temperature(_clamp(baseline.temperature + tint.temperature_delta, *_TEMPERATURE_RANGE))

    async def _restore_baseline(self) -> None:
        baseline = self._baseline
        self._active_tint = _ZERO_TINT
        self._active_tool_calls = 0
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
            self._hue_open = True
            await self._hue.connect()
            self._room = self._hue.rooms.from_name(self._room_name)
            logger.info("Hue listener bound to room %r", self._room_name)
        return self._room

    async def close(self) -> None:
        """Finish queued changes, detach from Hueify, and release the bridge connection."""
        await self._jobs.join()
        if self._worker is not None:
            self._worker.cancel()
            await asyncio.gather(self._worker, return_exceptions=True)
            self._worker = None
        self._event_bus.off(SessionStarted, self._on_session_started)
        self._event_bus.off(SessionEnded, self._on_session_ended)
        self._event_bus.off(UserTurnStarted, self._on_user_turn_started)
        self._event_bus.off(AssistantTurnStarted, self._on_assistant_turn_started)
        self._event_bus.off(ToolCallStarted, self._on_tool_call_started)
        self._event_bus.off(ToolCallFinished, self._on_tool_call_finished)
        self._hue.off(GroupedLightEvent, self._on_bridge_event)
        if self._hue_open:
            await self._hue.close()
            self._hue_open = False
        self._room = None


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
