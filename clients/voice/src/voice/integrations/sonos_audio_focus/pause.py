import asyncio
import logging

from sonosify import (
    AVTransportEvent,
    EventService,
    EventSubscription,
    SonosClient,
    TransportState,
)

from voice.integrations.sonos_audio_focus.policy import SonosAudioFocusPolicy

logger = logging.getLogger(__name__)


class SonosPausePolicy(SonosAudioFocusPolicy):
    """Yields audio focus by pausing active Sonos playback."""

    def __init__(
        self,
        *,
        client: SonosClient,
    ) -> None:
        super().__init__(client=client)
        self._active = False
        self._resume_allowed = False
        self._awaiting_initial_state = False
        self._subscription: EventSubscription | None = None
        self._watch_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    async def activate(self, *, reason: str) -> None:
        async with self._lock:
            if self._active:
                logger.debug("Sonos playback remains paused: %s", reason)
                return

            client = self._client
            transport = await client.get_transport_info()
            if transport.state is not TransportState.PLAYING:
                logger.debug(
                    "Leaving Sonos playback unchanged in state %s: %s",
                    transport.state,
                    reason,
                )
                return

            self._resume_allowed = True
            try:
                await client.pause()
            except Exception:
                self._resume_allowed = False
                raise
            self._active = True
            self._awaiting_initial_state = True
            await self._start_watching(client)
            logger.info("Sonos playback paused: %s", reason)

    async def deactivate(self, *, reason: str) -> None:
        async with self._lock:
            if not self._active:
                logger.debug("No Sonos playback to resume: %s", reason)
                return

            client = self._client
            try:
                await asyncio.sleep(0)
                transport = await client.get_transport_info()
                if (
                    self._resume_allowed
                    and transport.state is TransportState.PAUSED_PLAYBACK
                ):
                    await client.play()
                    logger.info("Sonos playback resumed: %s", reason)
                elif not self._resume_allowed:
                    logger.info(
                        "Not resuming Sonos playback because it was controlled "
                        "externally: %s",
                        reason,
                    )
                else:
                    logger.info(
                        "Not resuming Sonos playback because its state changed "
                        "to %s: %s",
                        transport.state,
                        reason,
                    )
            finally:
                self._active = False
                self._resume_allowed = False
                self._awaiting_initial_state = False
                await self._stop_watching()

    async def close(self) -> None:
        await self._stop_watching()
        await super().close()

    async def _start_watching(self, client: SonosClient) -> None:
        subscription: EventSubscription | None = None
        try:
            subscription = client.watch(services=(EventService.AV_TRANSPORT,))
            await subscription.start()
        except Exception:
            logger.exception(
                "Could not watch Sonos transport events; falling back to the "
                "final playback state"
            )
            if subscription is not None:
                await asyncio.gather(subscription.close(), return_exceptions=True)
            return

        self._subscription = subscription
        self._watch_task = asyncio.create_task(
            self._watch_transport(subscription),
            name="voice-sonos-transport-watch",
        )

    async def _stop_watching(self) -> None:
        watch_task, self._watch_task = self._watch_task, None
        subscription, self._subscription = self._subscription, None
        if watch_task is not None:
            watch_task.cancel()
            await asyncio.gather(watch_task, return_exceptions=True)
        if subscription is not None:
            await subscription.close()

    async def _watch_transport(self, subscription: EventSubscription) -> None:
        async for event in subscription:
            if not isinstance(event, AVTransportEvent):
                continue
            state = event.transport_state
            if self._awaiting_initial_state:
                self._awaiting_initial_state = False
                if state is TransportState.PAUSED_PLAYBACK:
                    continue

            self._resume_allowed = False
            logger.info(
                "Sonos transport was controlled externally during the voice turn: %s",
                state,
            )
