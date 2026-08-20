import logging
from abc import ABC, abstractmethod

from sonosify import SonosClient, SonosController

from voice.sonos import SonosSettings

logger = logging.getLogger(__name__)


class SonosAudioFocusPolicy(ABC):
    """Defines how Sonos yields audio focus during a voice interaction."""

    def __init__(
        self,
        *,
        settings: SonosSettings | None = None,
        client: SonosClient | None = None,
    ) -> None:
        self._settings = settings if settings is not None else SonosSettings()
        self._client = client
        self._owns_client = client is None

    async def prepare(self) -> None:
        if self._client is None:
            self._client = await SonosController().client(
                self._settings.speaker_name,
                ip=self._settings.ip_address,
            )
        logger.info(
            "Sonos audio focus policy ready for %s",
            self._settings.speaker_name or self._client.ip,
        )

    @abstractmethod
    async def activate(self, *, reason: str) -> None: ...

    @abstractmethod
    async def deactivate(self, *, reason: str) -> None: ...

    async def close(self) -> None:
        if self._client is not None and self._owns_client:
            logger.debug("Closing Sonos audio focus policy client")
            await self._client.close()
            self._client = None

    @property
    def _is_prepared(self) -> bool:
        return self._client is not None

    def _prepared_client(self) -> SonosClient:
        if self._client is None:
            raise RuntimeError("SonosAudioFocusPolicy must be prepared before use.")
        return self._client
