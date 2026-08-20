from abc import ABC, abstractmethod

_MIN_VOLUME = 0
_MAX_VOLUME = 100


class VolumeControl(ABC):
    """Optional audio output capability: playback volume in percent."""

    @abstractmethod
    async def get_volume(self) -> int: ...

    @abstractmethod
    async def set_volume(self, volume: int) -> None: ...


def clamp_volume(volume: int) -> int:
    return max(_MIN_VOLUME, min(_MAX_VOLUME, volume))
