from voice.vad import SileroVoiceActivityDetector


def test_silero_classifies_one_silent_frame_as_non_speech() -> None:
    detector = SileroVoiceActivityDetector()

    assert detector.is_speech(bytes(detector.frame_samples * 2)) is False
