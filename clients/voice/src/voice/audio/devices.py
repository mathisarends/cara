from abc import ABC, abstractmethod
from contextlib import AsyncExitStack
from dataclasses import dataclass

from voice.audio.ports import AudioInput, AudioOutput


@dataclass(frozen=True, slots=True)
class AudioDevices:
    input: AudioInput
    output: AudioOutput


class AudioDeviceFactory(ABC):
    @abstractmethod
    async def open(self, resources: AsyncExitStack) -> AudioDevices:
        """Open the devices, registering whatever must be closed on ``resources``."""
