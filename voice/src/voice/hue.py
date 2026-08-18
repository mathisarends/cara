import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from uuid import UUID

from hueify import GroupedLight, Hueify, Room
from hueify.models import HueEvent

from voice.observer import Observer, ObserverContext

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _LightingEffect:
    brightness_delta: float = 0
    temperature_delta: float = 0


@dataclass(frozen=True, slots=True)
class _Baseline:
    on: bool
    brightness: float
    temperature: float | None


class LightingState(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"


_EFFECTS = {
    LightingState.IDLE: _LightingEffect(),
    LightingState.LISTENING: _LightingEffect(
        brightness_delta=8,
        temperature_delta=-5,
    ),
    LightingState.PROCESSING: _LightingEffect(
        brightness_delta=-3,
        temperature_delta=5,
    ),
    LightingState.SPEAKING: _LightingEffect(
        brightness_delta=-3,
        temperature_delta=5,
    ),
}

_TRANSITIONS = {
    LightingState.IDLE: 0.5,
    LightingState.LISTENING: 0.2,
    LightingState.PROCESSING: 0.4,
    LightingState.SPEAKING: 0.4,
}

_BRIGHTNESS_RANGE = (0, 100)
_TEMPERATURE_RANGE = (0, 100)
_MIREK_MIN = 153
_MIREK_MAX = 500


class HueObserver(Observer):
    """Reflects the voice-agent lifecycle in a Hue room's existing lighting."""

    def __init__(
        self,
        room_name: str = "Mein Zimmer",
        *,
        hue: Hueify | None = None,
    ) -> None:
        self._room_name = room_name
        self._hue = hue or Hueify()
        self._room: Room | None = None
        self._grouped_light_id: UUID | None = None
        self._baseline: _Baseline | None = None
        self._state = LightingState.IDLE
        self._active_effect = _EFFECTS[LightingState.IDLE]
        self._jobs: asyncio.Queue[Callable[[], Awaitable[None]]] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None
        self._stream_started = False
        self._prepared = False

    async def prepare(self, context: ObserverContext) -> None:
        self._hue.on("grouped_light", self._on_bridge_event)
        try:
            self._room = await self._hue.rooms.find_by_name(self._room_name)
            grouped_light = await self._hue.rooms.grouped_light(self._room.id)
            self._capture_baseline(grouped_light)
            await self._hue.start_stream()
        except Exception:
            self._hue.off("grouped_light", self._on_bridge_event)
            self._room = None
            self._baseline = None
            raise
        self._stream_started = True
        self._prepared = True
        logger.info("Hue observer bound to room %r", self._room_name)

    async def on_wake_word_detected(
        self, name: str, score: float, sequence: int
    ) -> None:
        self._submit_state(LightingState.LISTENING)

    async def on_user_turn_started(self) -> None:
        self._submit_state(LightingState.LISTENING)

    async def on_assistant_turn_started(self) -> None:
        self._submit_state(LightingState.PROCESSING)

    async def on_assistant_tool_started(self, name: str) -> None:
        self._submit_state(LightingState.PROCESSING)

    async def on_assistant_tool_completed(self, name: str) -> None:
        self._submit_state(LightingState.PROCESSING)

    async def on_assistant_started_responding(self) -> None:
        self._submit_state(LightingState.SPEAKING)

    async def on_assistant_interrupted(self, turn_id: int) -> None:
        self._submit_state(LightingState.LISTENING)

    async def on_user_inactivity_timeout(self, timeout_seconds: float) -> None:
        self._submit_state(LightingState.IDLE)

    async def on_agent_error(self, turn_id: int, message: str) -> None:
        self._submit_state(LightingState.IDLE)

    async def on_voice_turn_timed_out(self, turn_id: int) -> None:
        self._submit_state(LightingState.IDLE)

    async def on_agent_stopped(self) -> None:
        if not self._prepared:
            return
        self._submit_state(LightingState.IDLE)
        await self._jobs.join()
        await self._stop_worker()
        self._hue.off("grouped_light", self._on_bridge_event)
        if self._stream_started:
            await self._hue.close()
        self._stream_started = False
        self._prepared = False
        self._room = None
        self._grouped_light_id = None
        self._baseline = None

    def _submit(self, job: Callable[[], Awaitable[None]]) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run(), name="voice-hue-observer")
        self._jobs.put_nowait(job)

    def _submit_state(self, state: LightingState) -> None:
        self._submit(lambda: self._set_state(state))

    async def _run(self) -> None:
        while True:
            job = await self._jobs.get()
            try:
                await job()
            except Exception:
                logger.exception("Hue operation failed")
            finally:
                self._jobs.task_done()

    async def _stop_worker(self) -> None:
        if self._worker is None:
            return
        self._worker.cancel()
        await asyncio.gather(self._worker, return_exceptions=True)
        self._worker = None

    def _capture_baseline(self, grouped_light: GroupedLight) -> None:
        self._grouped_light_id = grouped_light.id
        self._state = LightingState.IDLE
        self._active_effect = _EFFECTS[LightingState.IDLE]
        self._baseline = _Baseline(
            on=grouped_light.is_on is True,
            brightness=grouped_light.brightness or 0,
            temperature=_read_temperature(grouped_light),
        )

    async def _set_state(self, state: LightingState) -> None:
        baseline = self._baseline
        effect = _EFFECTS[state]
        if effect == self._active_effect:
            self._state = state
            return

        previous_state = self._state
        previous_effect = self._active_effect
        self._state = state
        self._active_effect = effect
        if baseline is None or not baseline.on:
            return

        temperature = (
            None
            if baseline.temperature is None
            else _percentage_to_mirek(
                _clamp(
                    baseline.temperature + effect.temperature_delta,
                    *_TEMPERATURE_RANGE,
                )
            )
        )
        try:
            await self._hue.rooms.set_state(
                self._room_id(),
                on=True,
                brightness=_clamp(
                    baseline.brightness + effect.brightness_delta,
                    *_BRIGHTNESS_RANGE,
                ),
                mirek=temperature,
                transition=_TRANSITIONS[state],
            )
        except Exception:
            self._state = previous_state
            self._active_effect = previous_effect
            raise

    async def _on_bridge_event(self, event: HueEvent) -> None:
        baseline = self._baseline
        if baseline is None or event.id != self._grouped_light_id:
            return

        grouped_light = GroupedLight.model_validate(event.model_dump())
        effect = self._active_effect
        if grouped_light.on is not None:
            baseline = replace(baseline, on=grouped_light.on.on)
        if grouped_light.dimming is not None:
            baseline = replace(
                baseline,
                brightness=_clamp(
                    grouped_light.dimming.brightness - effect.brightness_delta,
                    *_BRIGHTNESS_RANGE,
                ),
            )
        if grouped_light.mirek is not None:
            baseline = replace(
                baseline,
                temperature=_clamp(
                    _mirek_to_percentage(grouped_light.mirek)
                    - effect.temperature_delta,
                    *_TEMPERATURE_RANGE,
                ),
            )
        self._baseline = baseline

    def _room_id(self) -> UUID:
        if self._room is None:
            raise RuntimeError("HueObserver must be prepared before use.")
        return self._room.id


def _clamp(value: float, lower: int, upper: int) -> float:
    return max(lower, min(upper, value))


def _mirek_to_percentage(mirek: int) -> float:
    return ((mirek - _MIREK_MIN) / (_MIREK_MAX - _MIREK_MIN)) * 100


def _percentage_to_mirek(percentage: float) -> int:
    return round(_MIREK_MIN + (percentage / 100) * (_MIREK_MAX - _MIREK_MIN))


def _read_temperature(grouped_light: GroupedLight) -> float | None:
    if grouped_light.mirek is None:
        return None
    return _mirek_to_percentage(grouped_light.mirek)
