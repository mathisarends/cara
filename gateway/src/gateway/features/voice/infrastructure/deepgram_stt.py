from collections.abc import AsyncIterable, AsyncIterator

from gateway.features.voice.application import SpeechToText, Transcription
from stt.deepgram import SpeechToText as DeepgramClient
from stt.deepgram.events import TurnEagerEnd, TurnEnd, TurnUpdate


class DeepgramSpeechToText(SpeechToText):
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        sample_rate: int = 16_000,
    ) -> None:
        self._client = DeepgramClient(
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
