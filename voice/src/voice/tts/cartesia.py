from collections.abc import AsyncIterable, AsyncIterator
from typing import Any

from vocalbin.cartesia.tts import (
    TextToSpeech as _VocalbinTextToSpeech,
)

from voice.tts.port import TextToSpeech

_DEFAULT_VOICE_ID = "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4"


class CartesiaTextToSpeech(_VocalbinTextToSpeech, TextToSpeech):
    """Adapts Cartesia's incremental WebSocket stream to the TTS port."""

    def __init__(
        self,
        *,
        voice_id: str = _DEFAULT_VOICE_ID,
        language: str = "de",
        **kwargs: Any,
    ) -> None:
        super().__init__(voice_id=voice_id, language=language, **kwargs)

    async def synthesize(self, text: AsyncIterable[str]) -> AsyncIterator[bytes]:
        async for chunk in self.stream_incremental(text):
            yield chunk
