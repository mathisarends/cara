import logging
from dataclasses import replace
from uuid import UUID

from hueify import GroupedLight, Hueify, Room
from hueify.models import HueEvent

from voice.lights.hue.baseline import (
    BRIGHTNESS_RANGE,
    TEMPERATURE_RANGE,
    Baseline,
    capture_baseline,
    clamp,
    mirek_to_percentage,
    percentage_to_mirek,
)
from voice.lights.hue.effects import EFFECTS, TRANSITIONS
from voice.lights.state import LightingState

logger = logging.getLogger(__name__)


class HueRoomLighting:
    """Owns a Hue room's baseline and applies semantic lighting states."""

    def __init__(self, *, room_name: str, hue: Hueify) -> None:
        self._room_name = room_name
        self._hue = hue
        self._room: Room | None = None
        self._grouped_light_id: UUID | None = None
        self._baseline: Baseline | None = None
        self._state = LightingState.IDLE
        self._active_effect = EFFECTS[LightingState.IDLE]
        self._stream_started = False

    @property
    def is_prepared(self) -> bool:
        return self._stream_started

    async def prepare(self) -> None:
        self._hue.on("grouped_light", self._on_bridge_event)
        try:
            self._room = await self._hue.rooms.find_by_name(self._room_name)
            grouped_light = await self._hue.rooms.grouped_light(self._room.id)
            self._state = LightingState.IDLE
            self._active_effect = EFFECTS[LightingState.IDLE]
            self._grouped_light_id = grouped_light.id
            self._baseline = capture_baseline(grouped_light)
            await self._hue.start_stream()
        except Exception:
            self._hue.off("grouped_light", self._on_bridge_event)
            self._room = None
            self._baseline = None
            raise
        self._stream_started = True
        logger.info("Hue integration bound to room %r", self._room_name)

    async def set_state(self, state: LightingState) -> None:
        baseline = self._baseline
        effect = EFFECTS[state]
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
            else percentage_to_mirek(
                clamp(
                    baseline.temperature + effect.temperature_delta,
                    *TEMPERATURE_RANGE,
                )
            )
        )
        try:
            await self._hue.rooms.set_state(
                self._room_id(),
                on=True,
                brightness=clamp(
                    baseline.brightness + effect.brightness_delta,
                    *BRIGHTNESS_RANGE,
                ),
                mirek=temperature,
                transition=TRANSITIONS[state],
            )
        except Exception:
            self._state = previous_state
            self._active_effect = previous_effect
            raise

    async def close(self) -> None:
        self._hue.off("grouped_light", self._on_bridge_event)
        if self._stream_started:
            await self._hue.close()
        self._stream_started = False
        self._room = None
        self._grouped_light_id = None
        self._baseline = None

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
                brightness=clamp(
                    grouped_light.dimming.brightness - effect.brightness_delta,
                    *BRIGHTNESS_RANGE,
                ),
            )
        if grouped_light.mirek is not None:
            baseline = replace(
                baseline,
                temperature=clamp(
                    mirek_to_percentage(grouped_light.mirek) - effect.temperature_delta,
                    *TEMPERATURE_RANGE,
                ),
            )
        self._baseline = baseline

    def _room_id(self) -> UUID:
        if self._room is None:
            raise RuntimeError("Hue lighting must be prepared before use.")
        return self._room.id
