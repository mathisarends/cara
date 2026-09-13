from collections.abc import Iterator
from types import SimpleNamespace

import pytest


class _Detector:
    def __init__(self, detections: Iterator[object]) -> None:
        self._detections = detections
        self.calls: list[tuple[bytes, object]] = []
        self.reset_count = 0

    async def process(self, pcm: bytes, *, format: object) -> object:
        self.calls.append((pcm, format))
        return next(self._detections)

    def reset(self) -> None:
        self.reset_count += 1


@pytest.fixture
def detector_factory(monkeypatch):
    created: list[_Detector] = []

    def install(*detections: object) -> list[_Detector]:
        def create(*args: object, **kwargs: object) -> _Detector:
            detector = _Detector(iter(detections))
            created.append(detector)
            return detector

        monkeypatch.setattr("voice.wakeword.listener.WakeWordDetector", create)
        return created

    return install


@pytest.fixture
def detection_result():
    return SimpleNamespace(score=0.91, name="hey_mycroft")
