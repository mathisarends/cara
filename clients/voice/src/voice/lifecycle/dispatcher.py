import asyncio
import logging
from collections.abc import Iterable

from voice.lifecycle.events import VoiceLifecycleEvent
from voice.lifecycle.observer import VoiceLifecycleObserver

logger = logging.getLogger(__name__)


class LifecycleDispatcher:
    """Delivers lifecycle events to observers in order, off the control path.

    A slow observer, such as an earcon waiting for the output, delays later
    observations but never the session it observes.
    """

    def __init__(self, observers: Iterable[VoiceLifecycleObserver]) -> None:
        self._observers = tuple(observers)
        self._queue: asyncio.Queue[VoiceLifecycleEvent | None] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self._closed = False

    def start(self) -> None:
        if self._task is not None or self._closed:
            return
        self._task = asyncio.create_task(self._run(), name="voice-lifecycle")

    def publish(self, event: VoiceLifecycleEvent) -> None:
        if self._closed:
            return
        self._queue.put_nowait(event)

    async def aclose(self) -> None:
        """Deliver every published event, then stop."""
        if self._closed:
            return
        self._closed = True
        if self._task is None:
            return
        self._queue.put_nowait(None)
        await self._task

    async def _run(self) -> None:
        while (event := await self._queue.get()) is not None:
            for observer in self._observers:
                try:
                    await observer.on_lifecycle_event(event)
                except Exception:
                    logger.exception(
                        "%s failed to observe %s",
                        type(observer).__name__,
                        type(event).__name__,
                    )
