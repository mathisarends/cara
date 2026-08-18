from collections.abc import Callable
from typing import Protocol

from voice.echo_cancellation.timeline import PlaybackTimeline


class _Clock(Protocol):
    now: float

    def __call__(self) -> float: ...


def test_empty_timeline_reads_silence_and_ignores_discards(
    clock: _Clock,
) -> None:
    timeline = PlaybackTimeline(sample_rate=2, clock=clock)

    timeline.write(b"")
    timeline.discard_pending()

    assert timeline.read(0, 2) == bytes(4)


def test_reconstructs_gaps_and_reads_outside_the_buffer(
    clock: _Clock, pcm: Callable[..., bytes]
) -> None:
    timeline = PlaybackTimeline(sample_rate=2, clock=clock)
    timeline.write(pcm(1, 2))
    clock.now = 2.0
    timeline.write(pcm(3, 4))

    assert timeline.read(-0.5, 6) == pcm(0, 1, 2, 0, 0, 3)

    clock.now = 1.5
    timeline.write(pcm(8, 9, 10))

    assert timeline.read(0, 5) == pcm(1, 2, 0, 0, 3)


def test_discards_pending_audio_and_can_reset(
    clock: _Clock, pcm: Callable[..., bytes]
) -> None:
    timeline = PlaybackTimeline(sample_rate=2, clock=clock)
    timeline.write(pcm(1, 2, 3, 4))
    clock.now = 1.0

    timeline.discard_pending()
    assert timeline.read(0, 4) == pcm(1, 2, 0, 0)

    timeline.reset()
    assert timeline.read(0, 2) == bytes(4)


def test_trims_history_while_preserving_recent_samples(
    clock: _Clock, pcm: Callable[..., bytes]
) -> None:
    timeline = PlaybackTimeline(
        sample_rate=2,
        history_seconds=1,
        clock=clock,
    )
    timeline.write(pcm(1, 2, 3, 4))
    clock.now = 2.0
    timeline.write(pcm(5, 6))

    assert timeline.read(1.0, 4) == pcm(3, 4, 5, 6)

    clock.now = 10.0
    timeline.write(pcm(7, 8))

    assert timeline.read(10.0, 2) == pcm(7, 8)
