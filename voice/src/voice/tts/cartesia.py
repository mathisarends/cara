from collections.abc import AsyncIterable, AsyncIterator

from vocalbin.cartesia.tts import (
    AudioEncoding,
    BitRate,
    GenerationConfig,
    Mp3OutputFormat,
    OutputFormat,
    RawOutputFormat,
    SampleRate,
    TextToSpeechConfig,
    TextToSpeechError,
    TextToSpeechModel,
    TextToSpeechResponse,
    Voice,
    WavOutputFormat,
)
from vocalbin.cartesia.tts import (
    TextToSpeech as _VocalbinTextToSpeech,
)

from voice.tts.port import TextToSpeech


class CartesiaTextToSpeech(_VocalbinTextToSpeech, TextToSpeech):
    """Adapts Cartesia's incremental WebSocket stream to the TTS port."""

    async def synthesize(self, text: AsyncIterable[str]) -> AsyncIterator[bytes]:
        async for chunk in self.stream_incremental(text):
            yield chunk


__all__ = [
    "AudioEncoding",
    "BitRate",
    "CartesiaTextToSpeech",
    "GenerationConfig",
    "Mp3OutputFormat",
    "OutputFormat",
    "RawOutputFormat",
    "SampleRate",
    "TextToSpeechConfig",
    "TextToSpeechError",
    "TextToSpeechModel",
    "TextToSpeechResponse",
    "Voice",
    "WavOutputFormat",
]
