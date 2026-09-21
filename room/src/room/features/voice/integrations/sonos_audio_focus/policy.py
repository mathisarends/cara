import logging
from abc import ABC, abstractmethod

from sonosify import SonosClient

logger = logging.getLogger(__name__)


class SonosAudioFocusPolicy(ABC):
    """Defines how Sonos yields audio focus during a voice interaction."""

    def __init__(
        self,
        *,
        client: SonosClient,
    ) -> None:
        self._client = client

    async def prepare(self) -> None:
        logger.info("Sonos audio focus policy ready for %s", self._client.ip)

    @abstractmethod
    async def activate(self, *, reason: str) -> None: ...

    @abstractmethod
    async def deactivate(self, *, reason: str) -> None: ...
