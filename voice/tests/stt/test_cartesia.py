import asyncio
from collections.abc import AsyncIterator
from typing import cast

from cartesia import AsyncCartesia
from vocalbin.cartesia.events import Connected, TurnEagerEnd, TurnEnd, TurnUpdate
from vocalbin.cartesia.stt import SpeechToText as VocalbinSpeechToText

from voice.stt import CartesiaSpeechToText, Transcription, TranscriptionKind


async def _audio() -> AsyncIterator[bytes]:
    yield b"audio"


def test_transcribe_maps_cartesia_transcript_events(monkeypatch) -> None:
    async def stream(self, audio):
        assert [chunk async for chunk in audio] == [b"audio"]
        yield Connected(request_id="request")
        yield TurnUpdate(request_id="request", transcript="Hal")
        yield TurnEagerEnd(request_id="request", transcript="Hallo")
        yield TurnEnd(request_id="request", transcript="Hallo Cara")

    monkeypatch.setattr(VocalbinSpeechToText, "stream", stream)
    stt = CartesiaSpeechToText(client=cast(AsyncCartesia, object()))

    async def run() -> list[Transcription]:
        return [update async for update in stt.transcribe(_audio())]

    assert asyncio.run(run()) == [
        Transcription(text="Hal", is_final=False),
        Transcription("Hallo", False, TranscriptionKind.EAGER_END),
        Transcription("Hallo Cara", True, TranscriptionKind.END),
    ]
