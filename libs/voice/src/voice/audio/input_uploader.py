import asyncio
import logging

from voice.audio.buffered_input import AudioReader
from voice.backend import TurnRef, VoiceBackend

logger = logging.getLogger(__name__)


class TurnInputUploader:
    """Streams one turn's captured audio to the backend, then ends its input."""

    def __init__(
        self,
        backend: VoiceBackend,
        turn: TurnRef,
        reader: AudioReader,
        *,
        max_echo_confidence: float,
        end_after: float | None = None,
    ) -> None:
        if not 0.0 < max_echo_confidence <= 1.0:
            raise ValueError("max_echo_confidence must be within (0, 1]")
        self._backend = backend
        self._turn = turn
        self._reader = reader
        self._max_echo_confidence = max_echo_confidence
        self._end_after = end_after

    async def run(self) -> None:
        last_sequence = -1
        try:
            async with asyncio.timeout(self._end_after) as deadline:
                async for frame in self._reader:
                    last_sequence = frame.sequence
                    if frame.echo_confidence >= self._max_echo_confidence:
                        logger.debug(
                            "Suppressing input frame %d classified as playback echo "
                            "(confidence=%.2f)",
                            frame.sequence,
                            frame.echo_confidence,
                        )
                        continue
                    await self._backend.send_input(self._turn, frame)
        except TimeoutError:
            if not deadline.expired():
                raise
        finally:
            await self._reader.aclose()
        await self._backend.end_input(self._turn, last_sequence + 1)
