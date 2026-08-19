from collections.abc import AsyncIterable, AsyncIterator

from vocalbin.deepgram.events import (
    TurnEagerEnd,
    TurnEnd,
    TurnResume,
    TurnStart,
    TurnUpdate,
)
from vocalbin.deepgram.stt import StreamingSpeechToText as _VocalbinSpeechToText

from voice.stt.port import SpeechToText
from voice.transcription import Transcription, TranscriptionKind


class DeepgramSpeechToText(_VocalbinSpeechToText, SpeechToText):
    """Adapts Deepgram's streaming turn events to transcription updates."""

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
