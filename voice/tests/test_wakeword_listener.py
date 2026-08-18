import voice.wakeword.listener as listener_module
from voice.wakeword.listener import WakeWordListener


def _listener(*, cooldown: float = 1.5) -> WakeWordListener:
    listener = WakeWordListener.__new__(WakeWordListener)
    listener._cooldown = cooldown
    listener._last_detection_at = None
    return listener


def test_is_past_cooldown_blocks_detections_within_the_window(monkeypatch) -> None:
    listener = _listener(cooldown=1.5)
    times = iter([100.0, 100.4, 102.0])
    monkeypatch.setattr(listener_module.time, "monotonic", lambda: next(times))

    assert listener._is_past_cooldown() is True
    assert listener._is_past_cooldown() is False
    assert listener._is_past_cooldown() is True


def test_is_past_cooldown_survives_a_detector_reset(monkeypatch) -> None:
    """A detector.reset() (e.g. after an audio overrun) must not clear this."""
    listener = _listener(cooldown=1.5)
    listener._last_detection_at = 100.0
    monkeypatch.setattr(listener_module.time, "monotonic", lambda: 100.4)

    assert listener._is_past_cooldown() is False
