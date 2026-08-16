from collections.abc import AsyncIterable, AsyncIterator

from vocalbin.cartesia.events import TurnEagerEnd, TurnEnd, TurnUpdate
from vocalbin.cartesia.stt import (
    SpeechToText as _VocalbinSpeechToText,
)
from vocalbin.cartesia.stt import (
    SpeechToTextConfig,
    SpeechToTextEncoding,
    SpeechToTextError,
    SpeechToTextModel,
)

from voice.stt.port import SpeechToText, Transcription


class CartesiaSpeechToText(_VocalbinSpeechToText, SpeechToText):
    """Adapts Cartesia's streaming events to transcription updates."""

    async def transcribe(
        self, audio: AsyncIterable[bytes]
    ) -> AsyncIterator[Transcription]:
        async for event in self.stream(audio):
            match event:
                case TurnUpdate(transcript=text) | TurnEagerEnd(transcript=text):
                    yield Transcription(text=text, is_final=False)
                case TurnEnd(transcript=text):
                    yield Transcription(text=text, is_final=True)


__all__ = [
    "CartesiaSpeechToText",
    "SpeechToTextConfig",
    "SpeechToTextEncoding",
    "SpeechToTextError",
    "SpeechToTextModel",
]
