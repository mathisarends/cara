import asyncio

from voice.wakeword.ports import WakeWordDetectionSource


class WakeWordBargeIn:
    """Detects an interruption when an explicit wake word is spoken."""

    def __init__(self, wake_word_listener: WakeWordDetectionSource) -> None:
        self._wake_word_listener = wake_word_listener

    async def wait(self, *, cancel: asyncio.Event) -> None:
        score = await self._wake_word_listener.detect_once(cancel=cancel)
        if score is None and not cancel.is_set():
            await cancel.wait()
