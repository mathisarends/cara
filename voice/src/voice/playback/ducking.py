import asyncio
import logging

from sonosify import SonosClient, TransportState

from voice.playback.policy import SonosAudioFocusPolicy
from voice.sonos import SonosSettings

logger = logging.getLogger(__name__)

_DUCK_DURATION_MILLIS = 60_000
_DUCK_REFRESH_SECONDS = 45


class SonosDuckingPolicy(SonosAudioFocusPolicy):
    """Yields audio focus by lowering active Sonos playback."""

    def __init__(
        self,
        *,
        settings: SonosSettings | None = None,
        client: SonosClient | None = None,
    ) -> None:
        super().__init__(settings=settings, client=client)
        self._active = False
        self._refresh_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    async def activate(self, *, reason: str) -> None:
        async with self._lock:
            if self._active:
                logger.debug("Sonos playback remains ducked: %s", reason)
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

            await client.duck(_DUCK_DURATION_MILLIS)
            self._active = True
            self._refresh_task = asyncio.create_task(
                self._refresh(),
                name="voice-sonos-duck-refresh",
            )
            logger.info(
                "Sonos playback ducked for up to %d seconds: %s",
                _DUCK_DURATION_MILLIS // 1000,
                reason,
            )

    async def deactivate(self, *, reason: str) -> None:
        refresh_task: asyncio.Task[None] | None = None
        try:
            async with self._lock:
                if not self._is_prepared or not self._active:
                    logger.debug("No Sonos playback to unduck: %s", reason)
                    return

                refresh_task, self._refresh_task = self._refresh_task, None
                if refresh_task is not None:
                    refresh_task.cancel()

                await self._prepared_client().unduck()
                self._active = False
                logger.info("Sonos playback unducked: %s", reason)
        finally:
            if refresh_task is not None:
                await asyncio.gather(refresh_task, return_exceptions=True)

    async def _refresh(self) -> None:
        while True:
            await asyncio.sleep(_DUCK_REFRESH_SECONDS)
            async with self._lock:
                if not self._active:
                    return
                try:
                    await self._prepared_client().duck(_DUCK_DURATION_MILLIS)
                    logger.debug(
                        "Refreshed Sonos playback duck for %d seconds",
                        _DUCK_DURATION_MILLIS // 1000,
                    )
                except Exception:
                    logger.exception("Could not refresh Sonos playback duck")
