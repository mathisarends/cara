import logging

from transitbus import EventBus

from cara.events import SpeechChunkGenerated, Transcribed

logger = logging.getLogger(__name__)

_BRIGHT_CYAN = "\x1b[96m"
_BRIGHT_GREEN = "\x1b[92m"
_RESET = "\x1b[0m"


class ConsoleListener:
    """Writes conversational events to the console log."""

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._event_bus.subscribe(self._on_transcribed)
        self._event_bus.subscribe(self._on_speech_chunk_generated)

    async def _on_transcribed(self, event: Transcribed) -> None:
        logger.info("%s[heard] %s%s", _BRIGHT_CYAN, event.transcript, _RESET)

    async def _on_speech_chunk_generated(self, event: SpeechChunkGenerated) -> None:
        logger.info("%s[says] %s%s", _BRIGHT_GREEN, event.text, _RESET)
