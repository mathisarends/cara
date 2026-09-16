from dataclasses import dataclass

from hueify import GroupedLight

_BRIGHTNESS_RANGE = (0, 100)
_TEMPERATURE_RANGE = (0, 100)
_MIREK_MIN = 153
_MIREK_MAX = 500


@dataclass(frozen=True, slots=True)
class _Baseline:
    on: bool
    brightness: float
    temperature: float | None


def _capture_baseline(grouped_light: GroupedLight) -> _Baseline:
    return _Baseline(
        on=grouped_light.is_on is True,
        brightness=grouped_light.brightness or 0,
        temperature=_read_temperature(grouped_light),
    )


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
