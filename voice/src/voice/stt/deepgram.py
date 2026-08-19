from collections.abc import AsyncIterable, AsyncIterator
from typing import Any

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

# Deepgram waits 5s before forcing a turn to end when its confidence stays
# below the threshold. That is a phone-system timeout, not a conversational one.
_END_OF_TURN_TIMEOUT_MS = 2_000


class DeepgramSpeechToText(_VocalbinSpeechToText, SpeechToText):
    """Adapts Deepgram's streaming turn events to transcription updates."""

    def __init__(
        self,
        *,
        eot_timeout_ms: int = _END_OF_TURN_TIMEOUT_MS,
        **kwargs: Any,
    ) -> None:
        super().__init__(eot_timeout_ms=eot_timeout_ms, **kwargs)

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
