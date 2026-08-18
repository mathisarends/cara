from unittest.mock import Mock

from voice.vad import SileroVoiceActivityDetector


def test_delegates_detection_and_reset_to_silero(silero_backend: Mock) -> None:
    silero_backend.chunk_samples.return_value = 512
    silero_backend.process_chunk.return_value = 0.75
    detector = SileroVoiceActivityDetector()

    assert detector.sample_rate == 16_000
    assert detector.window_samples == 512
    assert detector.speech_probability(b"pcm") == 0.75
    detector.reset()

    silero_backend.process_chunk.assert_called_once_with(b"pcm")
    silero_backend.reset.assert_called_once_with()
