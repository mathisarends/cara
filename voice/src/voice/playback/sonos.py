import asyncio
import logging

from sonosify import SonosClient, SonosController, TransportState

from voice.observer import Observer, ObserverContext
from voice.sonos import SonosSettings

logger = logging.getLogger(__name__)


class SonosPlaybackObserver(Observer):
    """Pauses existing Sonos playback while a voice interaction is active."""

    def __init__(
        self,
        *,
        settings: SonosSettings | None = None,
        client: SonosClient | None = None,
    ) -> None:
        self._settings = settings or SonosSettings()
        self._client = client
        self._owns_client = client is None
        self._paused_by_observer = False
        self._lock = asyncio.Lock()

    async def prepare(self, context: ObserverContext) -> None:
        if self._client is None:
            controller = SonosController()
            self._client = await controller.client(
                self._settings.speaker_name,
                ip=self._settings.ip_address,
            )
        logger.info(
            "Sonos playback observer ready for %s",
            self._settings.speaker_name or self._client.ip,
        )

    async def on_wake_word_detected(
        self, name: str, score: float, sequence: int
    ) -> None:
        await self._pause(reason="wake word detected")

    async def on_user_turn_started(self) -> None:
        await self._pause(reason="user turn started")

    async def on_user_inactivity_timeout(self, timeout_seconds: float) -> None:
        await self._resume(reason="user inactivity timeout")

    async def on_agent_error(self, turn_id: int, message: str) -> None:
        await self._resume(reason=f"voice turn {turn_id} failed")

    async def on_voice_turn_timed_out(self, turn_id: int) -> None:
        await self._resume(reason=f"voice turn {turn_id} timed out")

    async def on_agent_stopped(self) -> None:
        try:
            await self._resume(reason="voice agent stopped")
        finally:
            if self._client is not None and self._owns_client:
                logger.debug("Closing Sonos playback observer client")
                await self._client.close()
                self._client = None

    async def _pause(self, *, reason: str) -> None:
        async with self._lock:
            if self._paused_by_observer:
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
            self._paused_by_observer = True
            logger.info(
                "Sonos playback %s -> %s: %s",
                TransportState.PLAYING,
                TransportState.PAUSED_PLAYBACK,
                reason,
            )

    async def _resume(self, *, reason: str) -> None:
        async with self._lock:
            if not self._paused_by_observer:
                logger.debug("No Sonos playback to resume: %s", reason)
                return

            client = self._prepared_client()
            transport = await client.get_transport_info()
            if transport.state is TransportState.PAUSED_PLAYBACK:
                await client.play()
                logger.info(
                    "Sonos playback %s -> %s: %s",
                    TransportState.PAUSED_PLAYBACK,
                    TransportState.PLAYING,
                    reason,
                )
            else:
                logger.info(
                    "Not resuming Sonos playback because its state changed to %s: %s",
                    transport.state,
                    reason,
                )
            self._paused_by_observer = False

    def _prepared_client(self) -> SonosClient:
        if self._client is None:
            raise RuntimeError("SonosPlaybackObserver must be prepared before use.")
        return self._client
