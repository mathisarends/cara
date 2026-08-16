import asyncio

from wakewordkit import Detection, WakeWord

from voice.wakeword import listener as listener_module
from voice.wakeword.listener import WakeWordListener


class RecordingMicrophone:
    def __init__(self) -> None:
        self.frame_sizes: list[int] = []

    def read(self, frame_size: int) -> bytes:
        self.frame_sizes.append(frame_size)
        return b"audio"

    def close(self) -> None:
        pass


class RecordingDetector:
    def __init__(self, wake_word: WakeWord, *, threshold: float) -> None:
        self.wake_word = wake_word
        self.threshold = threshold
        self.reset_calls = 0

    def reset(self) -> None:
        self.reset_calls += 1

    async def process(self, frame: bytes) -> Detection | None:
        assert frame == b"audio"
        return Detection(name="hey_mycroft", score=0.8)


def test_listener_adapts_shared_microphone_to_async_detector(monkeypatch) -> None:
    monkeypatch.setattr(listener_module, "WakeWordDetector", RecordingDetector)
    microphone = RecordingMicrophone()
    listener = WakeWordListener(
        microphone,
        wake_word=WakeWord.HEY_MYCROFT,
        sensitivity=0.6,
    )

    score = asyncio.run(listener.detect_once())

    assert score == 0.8
    assert microphone.frame_sizes == [1280]
    assert listener._detector.wake_word is WakeWord.HEY_MYCROFT
    assert listener._detector.threshold == 0.6
    assert listener._detector.reset_calls == 1


def test_listener_stops_after_current_read_when_cancelled(monkeypatch) -> None:
    monkeypatch.setattr(listener_module, "WakeWordDetector", RecordingDetector)
    microphone = RecordingMicrophone()
    listener = WakeWordListener(microphone)
    cancel = asyncio.Event()
    cancel.set()

    score = asyncio.run(listener.detect_once(cancel=cancel))

    assert score is None
    assert microphone.frame_sizes == []
