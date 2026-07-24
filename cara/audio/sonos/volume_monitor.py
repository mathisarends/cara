import asyncio
import contextlib
import logging

from sonosify import (
    EventService,
    EventSubscription,
    RenderingControlEvent,
    SonosEvent,
)

logger = logging.getLogger(__name__)

_MAX_SONOS_VOLUME = 100
# Sonos expires UPnP subscriptions after this many seconds; we renew earlier so
# the speaker keeps pushing NOTIFYs without a gap.
_SUBSCRIPTION_SECONDS = 300
_RENEW_AFTER_SECONDS = 240
_RETRY_DELAY = 5.0


class SonosVolumeMonitor:
    """Keeps a Sonos speaker's volume cached from local UPnP RenderingControl events.

    The cached value stays current whether the volume was changed by this program,
    the Sonos app, hardware buttons, or any other controller on the network.
    """

    def __init__(self, host: str) -> None:
        self._host = host
        self._volume: float | None = None
        self._task: asyncio.Task[None] | None = None

    @property
    def volume(self) -> float | None:
        """Last observed volume from 0.0 to 1.0, or ``None`` until the first event."""
        return self._volume

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run(), name="cara-sonos-volume-monitor")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run(self) -> None:
        while True:
            try:
                await self._listen_until_renewal()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Sonos volume subscription failed; retrying in %.0fs", _RETRY_DELAY)
                await asyncio.sleep(_RETRY_DELAY)

    async def _listen_until_renewal(self) -> None:
        loop = asyncio.get_running_loop()
        async with EventSubscription(
            self._host,
            services=(EventService.RENDERING_CONTROL,),
            timeout_seconds=_SUBSCRIPTION_SECONDS,
        ) as subscription:
            deadline = loop.time() + _RENEW_AFTER_SECONDS
            while (remaining := deadline - loop.time()) > 0:
                try:
                    event = await subscription.next_event(timeout=remaining)
                except TimeoutError:
                    return
                self._apply(event)

    def _apply(self, event: SonosEvent) -> None:
        if not isinstance(event, RenderingControlEvent) or event.volume is None:
            return
        self._volume = event.volume / _MAX_SONOS_VOLUME
        logger.debug("Sonos volume updated to %.2f", self._volume)
