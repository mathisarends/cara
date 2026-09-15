from collections.abc import AsyncIterable, AsyncIterator

from vocalbin.deepgram.events import TurnEagerEnd, TurnEnd, TurnUpdate
from vocalbin.deepgram.stt import StreamingSpeechToText

from gateway.features.voice.application import SpeechToText, Transcription


class DeepgramSpeechToText(SpeechToText):
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        sample_rate: int = 16_000,
    ) -> None:
        if api_key is None:
            self._client = StreamingSpeechToText(
                model=model,
                sample_rate=sample_rate,
                eot_timeout_ms=2_000,
            )
        else:
            self._client = StreamingSpeechToText(
                api_key,
                model=model,
                sample_rate=sample_rate,
                eot_timeout_ms=2_000,
            )

    async def transcribe(
        self,
        audio: AsyncIterable[bytes],
    ) -> AsyncIterator[Transcription]:
        async for event in self._client.stream(audio):
            match event:
                case TurnUpdate(transcript=text) | TurnEagerEnd(transcript=text):
                    yield Transcription(text, False)
                case TurnEnd(transcript=text):
                    yield Transcription(text, True)
