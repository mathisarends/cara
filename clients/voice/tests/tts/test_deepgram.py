import asyncio
from collections.abc import AsyncIterator
from typing import cast

from deepgram import AsyncDeepgramClient
from vocalbin.deepgram.tts import TextToSpeech as VocalbinTextToSpeech
from websockets.exceptions import ConnectionClosedError

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


def test_synthesize_reconnects_when_socket_closes_before_audio(monkeypatch) -> None:
    calls: list[list[str]] = []

    async def stream_incremental(self, text):
        calls.append([chunk async for chunk in text])
        if len(calls) == 1:
            raise ConnectionClosedError(None, None)
        yield b"reconnected"

    monkeypatch.setattr(VocalbinTextToSpeech, "stream_incremental", stream_incremental)
    tts = _deepgram()

    async def run() -> list[bytes]:
        return [chunk async for chunk in tts.synthesize(_text())]

    assert asyncio.run(run()) == [b"reconnected"]
    assert calls == [["Hallo ", "Cara"], ["Hallo ", "Cara"]]


def test_synthesize_opens_a_new_socket_after_an_idle_text_gap(monkeypatch) -> None:
    calls: list[list[str]] = []

    async def stream_incremental(self, text):
        chunks = [chunk async for chunk in text]
        calls.append(chunks)
        yield "".join(chunks).encode()

    async def text_with_gap() -> AsyncIterator[str]:
        yield "Ich schaue nach."
        await asyncio.sleep(0.02)
        yield "Gefunden."

    monkeypatch.setattr(VocalbinTextToSpeech, "stream_incremental", stream_incremental)
    tts = DeepgramTextToSpeech(
        client=cast(AsyncDeepgramClient, object()), segment_idle_seconds=0.001
    )

    async def run() -> list[bytes]:
        return [chunk async for chunk in tts.synthesize(text_with_gap())]

    assert asyncio.run(run()) == [b"Ich schaue nach.", b"Gefunden."]
    assert calls == [["Ich schaue nach."], ["Gefunden."]]


def test_voice_selects_the_deepgram_speech_model() -> None:
    tts = DeepgramTextToSpeech(
        client=cast(AsyncDeepgramClient, object()), voice=DeepgramVoice.AURA_2_ORION_EN
    )

    assert tts.default_config.model == "aura-2-orion-en"
