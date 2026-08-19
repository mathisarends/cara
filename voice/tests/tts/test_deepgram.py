import asyncio
from collections.abc import AsyncIterator
from typing import cast

from deepgram import AsyncDeepgramClient
from vocalbin.deepgram.tts import TextToSpeech as VocalbinTextToSpeech

from voice.tts import DeepgramTextToSpeech, DeepgramVoice


async def _text() -> AsyncIterator[str]:
    yield "Hallo "
    yield "Cara"


def _deepgram() -> DeepgramTextToSpeech:
    return DeepgramTextToSpeech(client=cast(AsyncDeepgramClient, object()))


def test_sample_rate_matches_the_requested_output_rate() -> None:
    assert _deepgram().sample_rate == 24_000
    assert (
        DeepgramTextToSpeech(
            client=cast(AsyncDeepgramClient, object()), sample_rate=16_000
        ).sample_rate
        == 16_000
    )


def test_synthesize_uses_the_incremental_deepgram_stream(monkeypatch) -> None:
    async def stream_incremental(self, text):
        assert [chunk async for chunk in text] == ["Hallo ", "Cara"]
        yield b"first"
        yield b"second"

    monkeypatch.setattr(VocalbinTextToSpeech, "stream_incremental", stream_incremental)
    tts = _deepgram()

    async def run() -> list[bytes]:
        return [chunk async for chunk in tts.synthesize(_text())]

    assert asyncio.run(run()) == [b"first", b"second"]


def test_voice_selects_the_deepgram_speech_model() -> None:
    tts = DeepgramTextToSpeech(
        client=cast(AsyncDeepgramClient, object()), voice=DeepgramVoice.AURA_2_ORION_EN
    )

    assert tts.default_config.model == "aura-2-orion-en"
