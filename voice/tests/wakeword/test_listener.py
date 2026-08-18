import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Protocol, cast

from wakewordkit import WakeWord

from voice.audio.buffered_input import AudioOverrunError, BufferedAudioInput
from voice.audio.models import AudioFrame
from voice.wakeword import WakeWordDetection, WakeWordSettings
from voice.wakeword.listener import WakeWordListener


class _Detector(Protocol):
    calls: list[tuple[bytes, "_DetectorFormat"]]
    reset_count: int


class _DetectorFormat(Protocol):
    sample_rate: int
    channels: int
    sample_format: str


class _DetectionResult(Protocol):
    score: float
    name: str


class _Reader:
    def __init__(
        self,
        owner: "_BufferedInput",
        items: list[AudioFrame | AudioOverrunError],
    ) -> None:
        self._owner = owner
        self._items = iter(items)
        self.closed = False

    def __aiter__(self) -> AsyncIterator[AudioFrame]:
        return self

    async def __anext__(self) -> AudioFrame:
        try:
            item = next(self._items)
        except StopIteration:
            self._owner.reader_finished()
            raise StopAsyncIteration from None
        if isinstance(item, AudioOverrunError):
            self._owner.reader_finished()
            raise item
        return item

    async def aclose(self) -> None:
        self.closed = True


class _BufferedInput:
    sample_rate = 16_000
    channels = 1
    chunk_seconds = 0.1

    def __init__(self, *readers: list[AudioFrame | AudioOverrunError]) -> None:
        self._pending = list(readers)
        self._running = True
        self.opened: list[_Reader] = []

    @property
    def is_running(self) -> bool:
        return self._running

    async def open_reader(self) -> _Reader:
        reader = _Reader(self, self._pending.pop(0))
        self.opened.append(reader)
        return reader

    def reader_finished(self) -> None:
        self._running = bool(self._pending)


def _listener(*, cooldown_chunks: int = 19) -> WakeWordListener:
    listener = WakeWordListener.__new__(WakeWordListener)
    listener._cooldown_chunks = cooldown_chunks
    listener._last_detection_sequence = None
    return listener


def test_is_past_cooldown_blocks_detections_within_the_chunk_window() -> None:
    listener = _listener(cooldown_chunks=19)

    assert listener._is_past_cooldown(56) is True
    assert (
        listener._is_past_cooldown(62) is False
    )  # 6 chunks later - still same utterance
    assert listener._is_past_cooldown(98) is True  # 36 chunks later - past cooldown


def test_is_past_cooldown_survives_a_sequence_jump_after_an_overrun() -> None:
    listener = _listener(cooldown_chunks=19)
    listener._last_detection_sequence = 62

    assert listener._is_past_cooldown(63) is False
    assert listener._is_past_cooldown(200) is True


def test_detects_configured_wake_word_and_applies_audio_cooldown(
    detector_factory: Callable[..., list[_Detector]],
    detection_result: _DetectionResult,
) -> None:
    created = detector_factory(detection_result, detection_result, None)
    buffered_input = _BufferedInput(
        [
            AudioFrame(sequence=1, pcm=b"first"),
            AudioFrame(sequence=2, pcm=b"same utterance"),
            AudioFrame(sequence=20, pcm=b"silence"),
        ]
    )
    listener = WakeWordListener(
        cast(BufferedAudioInput, buffered_input),
        settings=WakeWordSettings(wake_word=WakeWord.ALEXA, cooldown=1.5),
    )

    detections = asyncio.run(_collect(listener.detections()))

    assert listener.phrase == "alexa"
    assert [(item.sequence, item.score, item.name) for item in detections] == [
        (1, 0.91, "hey_mycroft")
    ]
    assert [call[0] for call in created[0].calls] == [
        b"first",
        b"same utterance",
        b"silence",
    ]
    detector_format = created[0].calls[0][1]
    assert detector_format.sample_rate == 16_000
    assert detector_format.channels == 1
    assert detector_format.sample_format == "pcm_s16le"
    assert buffered_input.opened[0].closed


def test_recovers_from_an_overrun_and_reopens_at_the_live_tail(
    detector_factory: Callable[..., list[_Detector]],
    detection_result: _DetectionResult,
    caplog,
) -> None:
    created = detector_factory(detection_result)
    buffered_input = _BufferedInput(
        [AudioOverrunError("reader fell behind")],
        [AudioFrame(sequence=200, pcm=b"live")],
    )
    listener = WakeWordListener(
        cast(BufferedAudioInput, buffered_input),
        settings=WakeWordSettings(),
    )

    detections = asyncio.run(_collect(listener.detections()))

    assert [item.sequence for item in detections] == [200]
    assert created[0].reset_count == 1
    assert all(reader.closed for reader in buffered_input.opened)
    assert "overran the audio buffer" in caplog.text


async def _collect(
    detections: AsyncIterator[WakeWordDetection],
) -> list[WakeWordDetection]:
    return [detection async for detection in detections]
