from collections.abc import AsyncIterable, AsyncIterator

from vocalbin.deepgram.tts import TextToSpeech as VocalbinTextToSpeech

from gateway.features.voice.application import TextToSpeech


class DeepgramTextToSpeech(TextToSpeech):
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        sample_rate: int = 24_000,
    ) -> None:
        self._client = VocalbinTextToSpeech(
            api_key,
            model=model,
            sample_rate=sample_rate,
        )

    async def synthesize(self, text: AsyncIterable[str]) -> AsyncIterator[bytes]:
        async for chunk in self._client.stream_incremental(text):
            if chunk:
                yield chunk
