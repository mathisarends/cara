import asyncio
from collections.abc import AsyncIterator

from vocalbin.cartesia.tts import TextToSpeech as VocalbinTextToSpeech

from voice.tts import CartesiaTextToSpeech


async def _text() -> AsyncIterator[str]:
    yield "Hallo "
    yield "Cara"


def test_synthesize_uses_incremental_cartesia_stream(monkeypatch) -> None:
    async def stream_incremental(self, text):
        assert [chunk async for chunk in text] == ["Hallo ", "Cara"]
        yield b"first"
        yield b"second"

    monkeypatch.setattr(VocalbinTextToSpeech, "stream_incremental", stream_incremental)
    tts = CartesiaTextToSpeech(client=object())

    async def run() -> list[bytes]:
        return [chunk async for chunk in tts.synthesize(_text())]

    assert asyncio.run(run()) == [b"first", b"second"]
