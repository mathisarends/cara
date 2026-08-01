import asyncio
import logging

from transitbus import EventBus

from cara.events import SpeechChunkGenerated, Transcribed
from cara.listener import ConsoleListener


def test_conversation_events_are_logged_with_distinct_colors(caplog) -> None:
    async def run() -> None:
        event_bus = EventBus()
        ConsoleListener(event_bus)

        await event_bus.dispatch(Transcribed(transcript="Hallo Welt"))
        await event_bus.dispatch(SpeechChunkGenerated(text="Hallo zurück"))

    with caplog.at_level(logging.INFO, logger="cara.listener.console_listener"):
        asyncio.run(run())

    assert "\x1b[96m[heard] Hallo Welt\x1b[0m" in caplog.messages
    assert "\x1b[92m[says] Hallo zurück\x1b[0m" in caplog.messages
