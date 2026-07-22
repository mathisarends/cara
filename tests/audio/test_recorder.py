import io
import threading
import time
import wave
from collections.abc import Callable

from cara.audio.recorder import MicrophoneInputSettings, MicrophoneRecorder

_RATE = 16_000
_FRAME_SAMPLES = 512
_FRAME = b"\x01\x00" * _FRAME_SAMPLES


class SequenceVoiceActivityDetector:
    sample_rate = _RATE
    frame_samples = _FRAME_SAMPLES

    def __init__(
        self,
        decisions: list[bool],
        *,
        on_decision: Callable[[int], None] | None = None,
    ) -> None:
        self._decisions = iter(decisions)
        self._on_decision = on_decision
        self._calls = 0
        self.reset_calls = 0

    def reset(self) -> None:
        self.reset_calls += 1

    def is_speech(self, frame: bytes) -> bool:
        assert len(frame) == _FRAME_SAMPLES * 2
        self._calls += 1
        if self._on_decision is not None:
            self._on_decision(self._calls)
        return next(self._decisions, False)


class SequenceTurnDetector:
    sample_rate = _RATE

    def __init__(self, decisions: list[bool]) -> None:
        self._decisions = iter(decisions)
        self.utterances: list[bytes] = []

    def is_complete(self, utterance: bytes) -> bool:
        self.utterances.append(utterance)
        return next(self._decisions)


class BlockingFirstTurnDetector(SequenceTurnDetector):
    def __init__(self, resumed: threading.Event) -> None:
        super().__init__([True])
        self._resumed = resumed

    def is_complete(self, utterance: bytes) -> bool:
        self.utterances.append(utterance)
        if len(self.utterances) == 1:
            assert self._resumed.wait(timeout=1.0)
        return True


class SequenceMicrophone:
    rate = _RATE
    channels = 1

    def __init__(
        self,
        *,
        delay: float = 0.002,
        on_read: Callable[[int], None] | None = None,
    ) -> None:
        self._delay = delay
        self._on_read = on_read
        self.reads = 0

    def read(self, num_frames: int) -> bytes:
        assert num_frames == _FRAME_SAMPLES
        self.reads += 1
        if self._on_read is not None:
            self._on_read(self.reads)
        time.sleep(self._delay)
        return _FRAME


class CancellingMicrophone(SequenceMicrophone):
    def __init__(self, cancel: threading.Event) -> None:
        super().__init__(delay=0.0)
        self._cancel = cancel

    def read(self, num_frames: int) -> bytes:
        frame = super().read(num_frames)
        self._cancel.set()
        return frame


def _settings(**overrides: float) -> MicrophoneInputSettings:
    values = {
        "candidate_silence_seconds": 0.064,
        "fallback_silence_seconds": 0.192,
        "min_record_seconds": 0.0,
        "max_record_seconds": 2.0,
    }
    values.update(overrides)
    return MicrophoneInputSettings(**values)


def _frame_count(audio: bytes) -> int:
    with wave.open(io.BytesIO(audio), "rb") as wav:
        return wav.getnframes()


def test_recorder_stops_when_cancelled_before_speech() -> None:
    cancel = threading.Event()
    microphone = CancellingMicrophone(cancel)
    vad = SequenceVoiceActivityDetector([True])
    recorder = MicrophoneRecorder(
        microphone,
        _settings(),
        vad=vad,
        turn_detector=SequenceTurnDetector([True]),
    )

    audio = recorder._record_until_silence_sync(cancel=cancel)

    assert audio is None
    assert microphone.reads == 1
    assert vad.reset_calls == 1


def test_complete_turn_ends_at_the_first_candidate_pause() -> None:
    microphone = SequenceMicrophone()
    detector = SequenceTurnDetector([True])
    recorder = MicrophoneRecorder(
        microphone,
        _settings(),
        vad=SequenceVoiceActivityDetector([True, True, False, False, False]),
        turn_detector=detector,
    )

    audio = recorder._record_until_silence_sync()

    assert audio is not None
    assert len(detector.utterances) == 1
    assert microphone.reads < 8
    assert _frame_count(audio) == microphone.reads * _FRAME_SAMPLES


def test_incomplete_turn_keeps_recording_across_a_thought_pause() -> None:
    microphone = SequenceMicrophone()
    detector = SequenceTurnDetector([False, True])
    recorder = MicrophoneRecorder(
        microphone,
        _settings(),
        vad=SequenceVoiceActivityDetector([True, True, False, False, False, True, True, False, False, False]),
        turn_detector=detector,
    )

    audio = recorder._record_until_silence_sync()

    assert audio is not None
    assert len(detector.utterances) == 2
    assert len(detector.utterances[1]) > len(detector.utterances[0])


def test_speech_resuming_during_inference_invalidates_the_old_answer() -> None:
    resumed = threading.Event()
    detector = BlockingFirstTurnDetector(resumed)
    vad = SequenceVoiceActivityDetector(
        [True, False, False, True, False, False, False],
        on_decision=lambda call: resumed.set() if call == 4 else None,
    )
    recorder = MicrophoneRecorder(
        SequenceMicrophone(),
        _settings(),
        vad=vad,
        turn_detector=detector,
    )

    audio = recorder._record_until_silence_sync()

    assert audio is not None
    assert len(detector.utterances) == 2
    assert len(detector.utterances[1]) > len(detector.utterances[0])


def test_long_silence_is_a_fallback_after_an_incomplete_answer() -> None:
    microphone = SequenceMicrophone()
    detector = SequenceTurnDetector([False])
    recorder = MicrophoneRecorder(
        microphone,
        _settings(),
        vad=SequenceVoiceActivityDetector([True]),
        turn_detector=detector,
    )

    audio = recorder._record_until_silence_sync()

    assert audio is not None
    assert len(detector.utterances) == 1
    assert microphone.reads == 7


def test_ready_event_suspends_endpoint_detection() -> None:
    ready = threading.Event()
    microphone = SequenceMicrophone(on_read=lambda read: ready.set() if read == 5 else None)
    detector = SequenceTurnDetector([True])
    recorder = MicrophoneRecorder(
        microphone,
        _settings(),
        vad=SequenceVoiceActivityDetector([True]),
        turn_detector=detector,
    )

    audio = recorder._record_until_silence_sync(ready=ready)

    assert audio is not None
    assert microphone.reads >= 7
    assert len(detector.utterances) == 1


def test_runaway_limit_replaces_the_old_twelve_second_cap() -> None:
    microphone = SequenceMicrophone()
    recorder = MicrophoneRecorder(
        microphone,
        _settings(max_record_seconds=0.16),
        vad=SequenceVoiceActivityDetector([True] * 20),
        turn_detector=SequenceTurnDetector([]),
    )

    audio = recorder._record_until_silence_sync()

    assert audio is not None
    assert microphone.reads == 5
    assert MicrophoneInputSettings().max_record_seconds == 90.0
