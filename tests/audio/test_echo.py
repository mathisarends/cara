import numpy as np
import pytest

from cara.audio import echo as echo_module
from cara.audio.echo import EchoCancellationSettings, WebRtcEchoCanceller


class RecordingAudioProcessor:
    def __init__(self, **options: bool) -> None:
        self.options = options
        self.render_frames: list[bytes] = []
        self.capture_frames: list[bytes] = []
        self.stream_format: tuple[int, int] | None = None
        self.reverse_stream_format: tuple[int, int] | None = None
        self.stream_delay: int | None = None

    def set_stream_format(self, sample_rate: int, channels: int) -> None:
        self.stream_format = sample_rate, channels

    def set_reverse_stream_format(self, sample_rate: int, channels: int) -> None:
        self.reverse_stream_format = sample_rate, channels

    def set_stream_delay(self, delay: int) -> None:
        self.stream_delay = delay

    def get_frame_size(self) -> int:
        return 160

    def process_reverse_stream(self, pcm: bytes) -> bytes:
        self.render_frames.append(pcm)
        return pcm

    def process_stream(self, pcm: bytes) -> bytes:
        self.capture_frames.append(pcm)
        return bytes(len(pcm))


def _echo_canceller(monkeypatch) -> tuple[WebRtcEchoCanceller, RecordingAudioProcessor]:
    processors: list[RecordingAudioProcessor] = []

    def create_processor(**options: bool) -> RecordingAudioProcessor:
        processor = RecordingAudioProcessor(**options)
        processors.append(processor)
        return processor

    monkeypatch.setattr(echo_module, "AudioProcessor", create_processor)
    canceller = WebRtcEchoCanceller(EchoCancellationSettings(stream_delay_ms=70))
    return canceller, processors[0]


def test_echo_canceller_feeds_resampled_speaker_reference(monkeypatch) -> None:
    canceller, processor = _echo_canceller(monkeypatch)
    left = np.full(480, 3000, dtype="<i2")
    right = np.full(480, 1000, dtype="<i2")
    stereo_48_khz = np.column_stack((left, right)).ravel().tobytes()

    canceller.analyze_render(
        stereo_48_khz,
        sample_rate=48000,
        channels=2,
        sample_width=2,
    )

    assert processor.reverse_stream_format == (16000, 1)
    assert processor.stream_delay == 70
    assert len(processor.render_frames) == 1
    assert np.frombuffer(processor.render_frames[0], dtype="<i2").tolist() == [2000] * 160


def test_echo_canceller_processes_capture_in_ten_millisecond_frames(monkeypatch) -> None:
    canceller, processor = _echo_canceller(monkeypatch)
    capture = b"\x01\x02" * 320

    cleaned = canceller.process_capture(capture)

    assert processor.capture_frames == [capture[:320], capture[320:]]
    assert cleaned == bytes(len(capture))


def test_echo_canceller_rejects_partial_capture_frame(monkeypatch) -> None:
    canceller, _ = _echo_canceller(monkeypatch)

    with pytest.raises(ValueError, match="complete 320-byte"):
        canceller.process_capture(b"partial")
