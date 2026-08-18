import asyncio
import logging

from sonosify import SonosClient, SonosController, TransportState

from voice.observer import Observer, ObserverContext
from voice.sonos import SonosSettings

logger = logging.getLogger(__name__)

_DUCK_DURATION_MILLIS = 60_000
_DUCK_REFRESH_SECONDS = 45


class SonosPlaybackObserver(Observer):
    """Ducks existing Sonos playback while a voice interaction is active."""

    def __init__(
        self,
        *,
        settings: SonosSettings | None = None,
        client: SonosClient | None = None,
    ) -> None:
        self._settings = settings or SonosSettings()
        self._client = client
        self._owns_client = client is None
        self._ducked_by_observer = False
        self._refresh_task: asyncio.Task[None] | None = None
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
        await self._start_ducking(reason="wake word detected")

    async def on_user_turn_started(self) -> None:
        await self._start_ducking(reason="user turn started")

    async def on_user_inactivity_timeout(self, timeout_seconds: float) -> None:
        await self._stop_ducking(reason="user inactivity timeout")

    async def on_agent_error(self, turn_id: int, message: str) -> None:
        await self._stop_ducking(reason=f"voice turn {turn_id} failed")

    async def on_voice_turn_timed_out(self, turn_id: int) -> None:
        await self._stop_ducking(reason=f"voice turn {turn_id} timed out")

    async def on_agent_stopped(self) -> None:
        try:
            await self._stop_ducking(reason="voice agent stopped")
        finally:
            if self._client is not None and self._owns_client:
                logger.debug("Closing Sonos playback observer client")
                await self._client.close()
                self._client = None

    async def _start_ducking(self, *, reason: str) -> None:
        async with self._lock:
            if self._ducked_by_observer:
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
            self._ducked_by_observer = True
            self._refresh_task = asyncio.create_task(
                self._refresh_ducking(),
                name="voice-sonos-duck-refresh",
            )
            logger.info(
                "Sonos playback ducked for up to %d seconds: %s",
                _DUCK_DURATION_MILLIS // 1000,
                reason,
            )

    async def _stop_ducking(self, *, reason: str) -> None:
        refresh_task: asyncio.Task[None] | None = None
        try:
            async with self._lock:
                if not self._ducked_by_observer:
                    logger.debug("No Sonos playback to unduck: %s", reason)
                    return

                refresh_task, self._refresh_task = self._refresh_task, None
                if refresh_task is not None:
                    refresh_task.cancel()

                await self._prepared_client().unduck()
                self._ducked_by_observer = False
                logger.info("Sonos playback unducked: %s", reason)
        finally:
            if refresh_task is not None:
                await asyncio.gather(refresh_task, return_exceptions=True)

    async def _refresh_ducking(self) -> None:
        while True:
            await asyncio.sleep(_DUCK_REFRESH_SECONDS)
            async with self._lock:
                if not self._ducked_by_observer:
                    return
                try:
                    await self._prepared_client().duck(_DUCK_DURATION_MILLIS)
                    logger.debug(
                        "Refreshed Sonos playback duck for %d seconds",
                        _DUCK_DURATION_MILLIS // 1000,
                    )
                except Exception:
                    logger.exception("Could not refresh Sonos playback duck")

    def _prepared_client(self) -> SonosClient:
        if self._client is None:
            raise RuntimeError("SonosPlaybackObserver must be prepared before use.")
        return self._client
