import asyncio
from collections.abc import AsyncIterator
from typing import cast
from uuid import uuid4

from doubles import CHUNK, EndInput, FakeVoiceBackend

from voice.audio import AudioFrame, AudioReader
from voice.audio.input_uploader import TurnInputUploader
from voice.backend import TurnRef

_TURN = TurnRef(uuid4())


class _Reader:
    def __init__(self, frames: list[AudioFrame], *, then_wait: bool = False) -> None:
        self._frames = frames
        self._then_wait = then_wait
        self.closed = False

    def __aiter__(self) -> AsyncIterator[AudioFrame]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[AudioFrame]:
        for frame in self._frames:
            yield frame
        if self._then_wait:
            await asyncio.Event().wait()

    async def aclose(self) -> None:
        self.closed = True


def _upload(reader: _Reader, *, end_after: float | None = None) -> FakeVoiceBackend:
    backend = FakeVoiceBackend()
    uploader = TurnInputUploader(
        backend,
        _TURN,
        cast(AudioReader, reader),
        max_echo_confidence=0.5,
        end_after=end_after,
    )
    asyncio.run(uploader.run())
    return backend


def test_uploads_frames_and_ends_input_after_the_last_one() -> None:
    reader = _Reader([AudioFrame(4, CHUNK), AudioFrame(5, CHUNK)])

    backend = _upload(reader)

    assert backend.inputs == [(_TURN, 4), (_TURN, 5)]
    assert backend.commands == [EndInput(_TURN, 6)]
    assert reader.closed


def test_suppresses_frames_classified_as_playback_echo() -> None:
    reader = _Reader(
        [
            AudioFrame(1, CHUNK, echo_confidence=0.9),
            AudioFrame(2, CHUNK, echo_confidence=0.1),
        ]
    )

    backend = _upload(reader)

    assert backend.inputs == [(_TURN, 2)]
    assert backend.commands == [EndInput(_TURN, 3)]


def test_ends_input_when_the_speech_start_timeout_expires() -> None:
    reader = _Reader([AudioFrame(0, CHUNK)], then_wait=True)

    backend = _upload(reader, end_after=0.01)

    assert backend.inputs == [(_TURN, 0)]
    assert backend.commands == [EndInput(_TURN, 1)]
    assert reader.closed
