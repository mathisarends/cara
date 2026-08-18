from collections.abc import AsyncIterable, AsyncIterator

from vocalbin.cartesia.events import (
    TurnEagerEnd,
    TurnEnd,
    TurnResume,
    TurnStart,
    TurnUpdate,
)
from vocalbin.cartesia.stt import SpeechToText as _VocalbinSpeechToText

from voice.stt.port import SpeechToText
from voice.transcription import Transcription, TranscriptionKind


class CartesiaSpeechToText(_VocalbinSpeechToText, SpeechToText):
    """Adapts Cartesia's streaming events to transcription updates."""

    async def transcribe(
        self, audio: AsyncIterable[bytes]
    ) -> AsyncIterator[Transcription]:
        async for event in self.stream(audio):
            match event:
                case TurnStart():
                    yield Transcription("", False, TranscriptionKind.START)
                case TurnUpdate(transcript=text):
                    yield Transcription(text, False, TranscriptionKind.UPDATE)
                case TurnEagerEnd(transcript=text):
                    yield Transcription(text, False, TranscriptionKind.EAGER_END)
                case TurnResume():
                    yield Transcription("", False, TranscriptionKind.RESUME)
                case TurnEnd(transcript=text):
                    yield Transcription(text, True, TranscriptionKind.END)
