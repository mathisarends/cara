import asyncio
from collections.abc import AsyncIterator
from typing import cast

from deepgram import AsyncDeepgramClient
from vocalbin.deepgram.events import Connected, TurnEagerEnd, TurnEnd, TurnUpdate
from vocalbin.deepgram.stt import StreamingSpeechToText as VocalbinSpeechToText

from voice.stt import DeepgramSpeechToText, Transcription, TranscriptionKind


async def _audio() -> AsyncIterator[bytes]:
    yield b"audio"


def test_transcribe_maps_deepgram_turn_events(monkeypatch) -> None:
    async def stream(self, audio):
        assert [chunk async for chunk in audio] == [b"audio"]
        yield Connected(request_id="request")
        yield TurnUpdate(
            request_id="request",
            turn_index=0,
            transcript="Hal",
            end_of_turn_confidence=0.1,
        )
        yield TurnEagerEnd(
            request_id="request",
            turn_index=0,
            transcript="Hallo",
            end_of_turn_confidence=0.7,
        )
        yield TurnEnd(
            request_id="request",
            turn_index=0,
            transcript="Hallo Cara",
            end_of_turn_confidence=0.9,
        )

    monkeypatch.setattr(VocalbinSpeechToText, "stream", stream)
    stt = DeepgramSpeechToText(client=cast(AsyncDeepgramClient, object()))

    async def run() -> list[Transcription]:
        return [update async for update in stt.transcribe(_audio())]

    assert asyncio.run(run()) == [
        Transcription(text="Hal", is_final=False),
        Transcription("Hallo", False, TranscriptionKind.EAGER_END),
        Transcription("Hallo Cara", True, TranscriptionKind.END),
    ]


def test_turns_end_sooner_than_deepgrams_phone_system_default() -> None:
    stt = DeepgramSpeechToText(client=cast(AsyncDeepgramClient, object()))

    assert stt.default_config.eot_timeout_ms == 2_000
