from abc import ABC, abstractmethod

from sound_generation.views import SoundEffectRequest, SoundEffectResponse


class SoundGenerator(ABC):
    @abstractmethod
    async def generate(self, request: SoundEffectRequest) -> SoundEffectResponse: ...
