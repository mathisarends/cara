from collections.abc import Callable

import pytest

from voice.echo_cancellation.reference import PlaybackReference


def test_empty_reference_reads_silence() -> None:
    reference = PlaybackReference(sample_rate=2)

    assert reference.read(0, 2) == bytes(4)


def test_reads_with_zero_padding_outside_available_samples(
    pcm: Callable[..., bytes],
) -> None:
    reference = PlaybackReference(sample_rate=2)
    reference.start_playback()
    reference.write(pcm(1, 2, 3, 4))

    assert reference.read(-1, 6) == pcm(0, 1, 2, 3, 4, 0)


def test_new_playback_replaces_the_previous_reference(
    pcm: Callable[..., bytes],
) -> None:
    reference = PlaybackReference(sample_rate=2)
    reference.start_playback()
    reference.write(pcm(1, 2))
    first_generation = reference.snapshot().generation

    reference.start_playback()
    reference.write(pcm(3, 4))

    snapshot = reference.snapshot()
    assert snapshot.generation == first_generation + 1
    assert snapshot.first_sample == 0
    assert snapshot.pcm == pcm(3, 4)


def test_trims_by_sample_count_and_preserves_absolute_positions(
    pcm: Callable[..., bytes],
) -> None:
    reference = PlaybackReference(sample_rate=2, history_seconds=1)
    reference.start_playback()
    reference.write(pcm(1, 2, 3, 4))

    snapshot = reference.snapshot()
    assert snapshot.first_sample == 2
    assert snapshot.pcm == pcm(3, 4)
    assert reference.read(1, 4) == pcm(0, 3, 4, 0)


def test_rejects_partial_samples() -> None:
    reference = PlaybackReference()

    with pytest.raises(ValueError, match="complete samples"):
        reference.write(b"x")
