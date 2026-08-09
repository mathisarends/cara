from cara.audio.turn_detection import SmartTurnDetector
from cara.audio.vad import SileroVoiceActivityDetector


def test_silero_classifies_one_silent_frame_as_non_speech() -> None:
    detector = SileroVoiceActivityDetector()

    assert detector.is_speech(bytes(detector.frame_samples * 2)) is False


def test_bundled_smart_turn_model_accepts_pcm_audio() -> None:
    detector = SmartTurnDetector()

    result = detector.is_complete(bytes(16_000 * 2))

    assert isinstance(result, bool)
