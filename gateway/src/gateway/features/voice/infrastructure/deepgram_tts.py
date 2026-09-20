from collections.abc import AsyncIterable, AsyncIterator

from gateway.features.voice.application import TextToSpeech
from tts.deepgram import TextToSpeech as DeepgramClient


class DeepgramTextToSpeech(TextToSpeech):
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        sample_rate: int = 24_000,
    ) -> None:
        self._client = DeepgramClient(
            api_key,
            model=model,
            sample_rate=sample_rate,
        )

    async def warmup(self) -> None:
        await self._client.warmup()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def synthesize(self, text: AsyncIterable[str]) -> AsyncIterator[bytes]:
        async for chunk in self._client.stream_incremental(text):
            if chunk:
                yield chunk
