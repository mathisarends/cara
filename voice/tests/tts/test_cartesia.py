import asyncio
from collections.abc import AsyncIterator

from vocalbin.cartesia.tts import TextToSpeech as VocalbinTextToSpeech

from voice.tts import CartesiaTextToSpeech, CartesiaVoice


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


def test_voice_selects_the_cartesia_voice_id() -> None:
    tts = CartesiaTextToSpeech(client=object(), voice=CartesiaVoice.ALARIC_WIZARD)

    assert tts.default_config.voice_id == "87748186-23bb-4158-a1eb-332911b0b708"
