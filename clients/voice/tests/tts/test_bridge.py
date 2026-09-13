import asyncio
from collections.abc import AsyncIterable, AsyncIterator

from voice.events import (
    AssistantAudioStarted,
    AssistantResponseStarted,
    AssistantTextChunk,
    AssistantTextCompleted,
)
from voice.events.bus import EventBus
from voice.tts import TextToSpeech, TextToSpeechBridge


class _TextToSpeech(TextToSpeech):
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    @property
    def sample_rate(self) -> int:
        return 24_000

    async def synthesize(self, text: AsyncIterable[str]) -> AsyncIterator[bytes]:
        chunks = [chunk async for chunk in text]
        self.calls.append(chunks)
        yield "".join(chunks).encode()


def test_defers_synthesis_until_text_arrives() -> None:
    async def run() -> tuple[list[AssistantAudioStarted], list[list[str]]]:
        event_bus = EventBus()
        text_to_speech = _TextToSpeech()
        TextToSpeechBridge(event_bus=event_bus, text_to_speech=text_to_speech)
        started: list[AssistantAudioStarted] = []

        async def capture(event: AssistantAudioStarted) -> None:
            started.append(event)

        event_bus.on(AssistantAudioStarted, capture)

        await event_bus.dispatch(AssistantResponseStarted(turn_id=8))
        await asyncio.sleep(0)
        assert started == []
        assert text_to_speech.calls == []

        await event_bus.dispatch(AssistantTextChunk(turn_id=8, chunk="Done."))
        await event_bus.dispatch(AssistantTextCompleted(turn_id=8, text="Done."))
        return started, text_to_speech.calls

    started, calls = asyncio.run(run())

    assert started == [AssistantAudioStarted(turn_id=8, sample_rate=24_000)]
    assert calls == [["Done."]]
