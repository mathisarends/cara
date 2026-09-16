from dataclasses import dataclass

from voice.lights.state import LightingState


@dataclass(frozen=True, slots=True)
class _LightingEffect:
    brightness_delta: float = 0
    temperature_delta: float = 0


EFFECTS = {
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

TRANSITIONS = {
    LightingState.IDLE: 0.5,
    LightingState.LISTENING: 0.2,
    LightingState.PROCESSING: 0.4,
    LightingState.SPEAKING: 0.4,
}
