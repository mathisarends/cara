from collections.abc import Callable

import numpy as np

from voice.echo_cancellation.alignment import ReferenceAligner
from voice.echo_cancellation.reference import PlaybackReference

_SAMPLE_RATE = 8_000
_CHUNK_SAMPLES = 800


def test_finds_playback_without_a_latency_estimate(
    pcm: Callable[..., bytes],
) -> None:
    rng = np.random.default_rng(7)
    playback = rng.integers(-12_000, 12_001, 3 * _SAMPLE_RATE, dtype=np.int16)
    reference = _reference(playback)
    aligner = _aligner(reference)
    heard_start = 13_600

    first = aligner.read(pcm(*playback[heard_start : heard_start + _CHUNK_SAMPLES]))
    second = aligner.read(
        pcm(*playback[heard_start + _CHUNK_SAMPLES : heard_start + 2 * _CHUNK_SAMPLES])
    )

    assert first == bytes(len(first))
    assert second == pcm(
        *playback[heard_start + _CHUNK_SAMPLES : heard_start + 2 * _CHUNK_SAMPLES]
    )
    assert aligner.is_aligned


def test_tracks_from_the_matched_sample_position(
    pcm: Callable[..., bytes],
) -> None:
    rng = np.random.default_rng(11)
    playback = rng.integers(-10_000, 10_001, 4 * _SAMPLE_RATE, dtype=np.int16)
    reference = _reference(playback)
    aligner = _aligner(reference)
    heard_start = 20_000

    references = []
    for start in range(heard_start, heard_start + 5 * _CHUNK_SAMPLES, _CHUNK_SAMPLES):
        references.append(aligner.read(pcm(*playback[start : start + _CHUNK_SAMPLES])))

    assert references[-1] == pcm(
        *playback[heard_start + 4 * _CHUNK_SAMPLES : heard_start + 5 * _CHUNK_SAMPLES]
    )


def test_does_not_align_unrelated_near_end_speech(
    pcm: Callable[..., bytes],
) -> None:
    rng = np.random.default_rng(19)
    reference = _reference(
        rng.integers(-12_000, 12_001, 3 * _SAMPLE_RATE, dtype=np.int16)
    )
    aligner = _aligner(reference)
    unrelated = rng.integers(-12_000, 12_001, 2 * _CHUNK_SAMPLES, dtype=np.int16)

    aligner.read(pcm(*unrelated[:_CHUNK_SAMPLES]))
    result = aligner.read(pcm(*unrelated[_CHUNK_SAMPLES:]))

    assert result == bytes(len(result))
    assert not aligner.is_aligned


def test_new_playback_invalidates_the_previous_alignment(
    pcm: Callable[..., bytes],
) -> None:
    rng = np.random.default_rng(23)
    playback = rng.integers(-12_000, 12_001, 3 * _SAMPLE_RATE, dtype=np.int16)
    reference = _reference(playback)
    aligner = _aligner(reference)
    for start in range(0, 2 * _CHUNK_SAMPLES, _CHUNK_SAMPLES):
        aligner.read(pcm(*playback[start : start + _CHUNK_SAMPLES]))
    assert aligner.is_aligned

    reference.start_playback()

    result = aligner.read(bytes(_CHUNK_SAMPLES * 2))
    assert result == bytes(len(result))
    assert not aligner.is_aligned


def _reference(samples: np.ndarray) -> PlaybackReference:
    reference = PlaybackReference(_SAMPLE_RATE)
    reference.start_playback()
    reference.write(samples.astype("<i2").tobytes())
    return reference


def _aligner(reference: PlaybackReference) -> ReferenceAligner:
    return ReferenceAligner(
        reference,
        window_seconds=0.2,
        interval_seconds=0.1,
        filter_headroom_seconds=0.0,
        min_correlation=0.5,
        analysis_sample_rate=_SAMPLE_RATE,
    )
