import asyncio
import logging
from contextlib import AsyncExitStack

from sonosify import SonosClient

from room.features.health.application import ReadinessService
from room.features.voice.integrations import (
    HueIntegration,
    SonosAudioFocusIntegration,
    SonosDuckingPolicy,
    SonosPausePolicy,
)
from voice import VoiceSession, VoiceSessionConfig, VoiceSessionFactory
from voice.config import SonosAudioFocusStrategy
from voice.integrations import VoiceIntegration

logger = logging.getLogger(__name__)


class RoomVoiceService:
    def __init__(
        self,
        voice_config: VoiceSessionConfig | None,
        readiness_service: ReadinessService,
        *,
        initial_retry_seconds: float = 1.0,
        maximum_retry_seconds: float = 30.0,
    ) -> None:
        self._voice_config = voice_config
        self._readiness_service = readiness_service
        self._voice_session: VoiceSession | None = None
        self._voice_task: asyncio.Task[None] | None = None
        self._room_resources: AsyncExitStack | None = None
        self._initial_retry_seconds = initial_retry_seconds
        self._maximum_retry_seconds = maximum_retry_seconds
        self._stopped = asyncio.Event()
        self._running = False

    async def run(self) -> None:
        if self._running:
            raise RuntimeError("Room Voice service is already running")
        self._running = True
        if self._voice_config is None:
            logger.warning("Voice is not configured for this Room process")
            await self._stopped.wait()
            return

        try:
            delay = self._initial_retry_seconds
            while not self._stopped.is_set():
                try:
                    await self._run_session()
                    delay = self._initial_retry_seconds
                    if not self._stopped.is_set():
                        logger.warning("Room voice runtime stopped unexpectedly")
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Room voice runtime failed; restarting")
                if await self._wait_for_retry(delay):
                    return
                delay = min(delay * 2, self._maximum_retry_seconds)
        finally:
            self._running = False
            self._readiness_service.voice_ready(False)
            await self._close_session()

    async def stop(self) -> None:
        self._stopped.set()
        self._readiness_service.voice_ready(False)
        voice_session = self._voice_session
        if voice_session is not None:
            await voice_session.close()

    async def _run_session(self) -> None:
        assert self._voice_config is not None
        room_resources = AsyncExitStack()
        await room_resources.__aenter__()
        try:
            integrations, sonos_client = await self._open_integrations(room_resources)
            voice_session_factory = VoiceSessionFactory(
                self._voice_config,
                integrations=integrations,
                accept_activations=lambda: self._readiness_service.snapshot().ready,
                sonos_client=sonos_client,
            )
            voice_session = await voice_session_factory.create()
        except BaseException:
            await room_resources.aclose()
            raise

        voice_task = asyncio.create_task(
            voice_session.run(),
            name="room-voice-runtime",
        )
        self._voice_session = voice_session
        self._voice_task = voice_task
        self._room_resources = room_resources
        try:
            await voice_session.wait_started()
            self._readiness_service.voice_ready(True)
            logger.info("Room voice runtime started")
            await voice_task
        finally:
            self._readiness_service.voice_ready(False)
            await self._close_session()

    async def _close_session(self) -> None:
        voice_session, self._voice_session = self._voice_session, None
        voice_task, self._voice_task = self._voice_task, None
        room_resources, self._room_resources = self._room_resources, None
        if voice_session is not None:
            await voice_session.close()
        if voice_task is not None:
            await asyncio.gather(voice_task, return_exceptions=True)
        if room_resources is not None:
            await room_resources.aclose()

    async def _wait_for_retry(self, delay: float) -> bool:
        try:
            await asyncio.wait_for(self._stopped.wait(), timeout=delay)
        except TimeoutError:
            return False
        return True

    async def _open_integrations(
        self,
        room_resources: AsyncExitStack,
    ) -> tuple[tuple[VoiceIntegration, ...], SonosClient | None]:
        assert self._voice_config is not None
        settings = self._voice_config.integrations
        integrations: list[VoiceIntegration] = []
        if settings.hue.enabled:
            integrations.append(HueIntegration(room_name=settings.hue.room_name))

        sonos_client = None
        if settings.sonos_audio_focus.enabled:
            sonos = self._voice_config.sonos
            if sonos is None:
                raise RuntimeError(
                    "Validated Voice configuration has no Sonos settings"
                )
            sonos_client = SonosClient(sonos.ip_address)
            await room_resources.enter_async_context(sonos_client)
            if settings.sonos_audio_focus.strategy is SonosAudioFocusStrategy.DUCK:
                policy = SonosDuckingPolicy(client=sonos_client)
            else:
                policy = SonosPausePolicy(client=sonos_client)
            integrations.append(SonosAudioFocusIntegration(policy=policy))
        return tuple(integrations), sonos_client
