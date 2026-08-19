from collections.abc import AsyncIterable, AsyncIterator
from typing import Any

from vocalbin.deepgram.tts import TextToSpeech as _VocalbinTextToSpeech
from vocalbin.deepgram.tts import TextToSpeechModel as DeepgramVoice

from voice.tts.port import TextToSpeech

_DEFAULT_VOICE = DeepgramVoice.AURA_2_THALIA_EN
_DEFAULT_SAMPLE_RATE = 24_000


class DeepgramTextToSpeech(_VocalbinTextToSpeech, TextToSpeech):
    """Adapts Deepgram's incremental WebSocket stream to the TTS port."""

    def __init__(
        self,
        *,
        voice: DeepgramVoice | str = _DEFAULT_VOICE,
        sample_rate: int = _DEFAULT_SAMPLE_RATE,
        **kwargs: Any,
    ) -> None:
        super().__init__(model=voice, sample_rate=sample_rate, **kwargs)
        self._sample_rate = sample_rate

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    async def synthesize(self, text: AsyncIterable[str]) -> AsyncIterator[bytes]:
        async for chunk in self.stream_incremental(text):
            yield chunk
