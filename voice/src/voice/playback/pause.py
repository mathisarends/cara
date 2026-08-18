import asyncio
import logging

from sonosify import SonosClient, TransportState

from voice.playback.strategy import PlaybackStrategy
from voice.sonos import SonosSettings

logger = logging.getLogger(__name__)


class PauseStrategy(PlaybackStrategy):
    """Pauses active playback and resumes only playback it paused itself."""

    def __init__(
        self,
        *,
        settings: SonosSettings | None = None,
        client: SonosClient | None = None,
    ) -> None:
        super().__init__(settings=settings, client=client)
        self._active = False
        self._lock = asyncio.Lock()

    async def activate(self, *, reason: str) -> None:
        async with self._lock:
            if self._active:
                logger.debug("Sonos playback remains paused: %s", reason)
                return

            client = self._prepared_client()
            transport = await client.get_transport_info()
            if transport.state is not TransportState.PLAYING:
                logger.debug(
                    "Leaving Sonos playback unchanged in state %s: %s",
                    transport.state,
                    reason,
                )
                return

            await client.pause()
            self._active = True
            logger.info("Sonos playback paused: %s", reason)

    async def deactivate(self, *, reason: str) -> None:
        async with self._lock:
            if not self._is_prepared or not self._active:
                logger.debug("No Sonos playback to resume: %s", reason)
                return

            client = self._prepared_client()
            transport = await client.get_transport_info()
            if transport.state is TransportState.PAUSED_PLAYBACK:
                await client.play()
                logger.info("Sonos playback resumed: %s", reason)
            else:
                logger.info(
                    "Not resuming Sonos playback because its state changed to %s: %s",
                    transport.state,
                    reason,
                )
            self._active = False
