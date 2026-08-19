from collections.abc import AsyncIterable, AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vocalbin.piper.tts import TextToSpeech as _VocalbinTextToSpeech

from voice.tts.port import TextToSpeech

if TYPE_CHECKING:
    from piper import PiperVoice

_BOUNDARY_CHARACTERS = ".!?…\n"
_MIN_SEGMENT_CHARACTERS = 40


class PiperTextToSpeech(_VocalbinTextToSpeech, TextToSpeech):
    """Adapts Piper's local sentence-based synthesis to the streaming TTS port."""

    def __init__(self, voice: "str | Path | PiperVoice", **kwargs: Any) -> None:
        if isinstance(voice, str | Path):
            super().__init__(voice, **kwargs)
        else:
            super().__init__(voice=voice, **kwargs)

    @property
    def sample_rate(self) -> int:
        return self.voice.config.sample_rate

    async def synthesize(self, text: AsyncIterable[str]) -> AsyncIterator[bytes]:
        pending = ""
        async for delta in text:
            pending += delta
            segment, pending = _split_completed_segment(pending)
            if segment:
                async for chunk in self.stream(segment):
                    yield chunk
        if pending.strip():
            async for chunk in self.stream(pending):
                yield chunk


def _split_completed_segment(pending: str) -> tuple[str, str]:
    """Split off the longest leading run of finished sentences worth synthesizing."""
    for index in range(len(pending) - 1, 0, -1):
        if (
            pending[index - 1] not in _BOUNDARY_CHARACTERS
            or not pending[index].isspace()
        ):
            continue
        segment = pending[:index].strip()
        if len(segment) < _MIN_SEGMENT_CHARACTERS:
            return "", pending
        return segment, pending[index:].lstrip()
    return "", pending
