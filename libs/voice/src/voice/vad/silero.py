from pysilero_vad import SileroVoiceActivityDetector as _SileroDetector

from voice.vad.port import VoiceActivityDetector

_SAMPLE_RATE = 16_000


class SileroVoiceActivityDetector(VoiceActivityDetector):
    """Silero VAD v5, running on onnxruntime with the bundled ONNX model."""

    def __init__(self) -> None:
        self._detector = _SileroDetector()

    @property
    def sample_rate(self) -> int:
        return _SAMPLE_RATE

    @property
    def window_samples(self) -> int:
        return self._detector.chunk_samples()

    def speech_probability(self, window: bytes) -> float:
        return self._detector.process_chunk(window)

    def reset(self) -> None:
        self._detector.reset()
