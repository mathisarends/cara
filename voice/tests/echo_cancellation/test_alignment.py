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


def test_reports_playback_that_dominates_the_microphone(
    pcm: Callable[..., bytes],
) -> None:
    rng = np.random.default_rng(29)
    playback = rng.integers(-12_000, 12_001, 3 * _SAMPLE_RATE, dtype=np.int16)
    aligner = _aligner(_reference(playback))
    heard_start = 9_600

    for start in range(heard_start, heard_start + 3 * _CHUNK_SAMPLES, _CHUNK_SAMPLES):
        aligner.read(pcm(*playback[start : start + _CHUNK_SAMPLES]))

    assert aligner.echo_confidence > 0.9


def test_playback_shares_the_microphone_with_a_speaking_user(
    pcm: Callable[..., bytes],
) -> None:
    rng = np.random.default_rng(31)
    playback = rng.integers(-12_000, 12_001, 3 * _SAMPLE_RATE, dtype=np.int16)
    aligner = _aligner(_reference(playback))
    heard_start = 9_600

    confidences = []
    for start in range(heard_start, heard_start + 3 * _CHUNK_SAMPLES, _CHUNK_SAMPLES):
        echo = playback[start : start + _CHUNK_SAMPLES].astype(np.int64)
        user = rng.integers(-12_000, 12_001, _CHUNK_SAMPLES, dtype=np.int64)
        heard = np.clip(echo + user, -32_768, 32_767).astype(np.int16)
        aligner.read(pcm(*heard))
        confidences.append(aligner.echo_confidence)

    # The echo is still found, but no longer explains the whole window.
    assert aligner.is_aligned
    assert 0.5 < max(confidences) < 0.9


def test_recovers_from_an_alignment_that_stopped_matching(
    pcm: Callable[..., bytes],
) -> None:
    rng = np.random.default_rng(37)
    playback = rng.integers(-12_000, 12_001, 6 * _SAMPLE_RATE, dtype=np.int16)
    aligner = _aligner(_reference(playback))

    for start in range(0, 3 * _CHUNK_SAMPLES, _CHUNK_SAMPLES):
        aligner.read(pcm(*playback[start : start + _CHUNK_SAMPLES]))
    assert aligner.is_aligned

    # Playback jumps far beyond the tracking window, as a buffering network
    # speaker does. The old lock can never explain these samples again.
    jumped = 4 * _SAMPLE_RATE
    references = []
    for start in range(jumped, jumped + 5 * _CHUNK_SAMPLES, _CHUNK_SAMPLES):
        references.append(aligner.read(pcm(*playback[start : start + _CHUNK_SAMPLES])))

    assert aligner.echo_confidence > 0.9
    assert references[-1] == pcm(
        *playback[jumped + 4 * _CHUNK_SAMPLES : jumped + 5 * _CHUNK_SAMPLES]
    )


def test_keeps_the_alignment_across_a_pause_in_the_playback(
    pcm: Callable[..., bytes],
) -> None:
    rng = np.random.default_rng(43)
    playback = rng.integers(-12_000, 12_001, 6 * _SAMPLE_RATE, dtype=np.int16)
    silence = 2 * _SAMPLE_RATE
    playback[silence : silence + _SAMPLE_RATE] = 0
    aligner = _aligner(_reference(playback))

    confidences = []
    for start in range(0, 6 * _SAMPLE_RATE - _CHUNK_SAMPLES, _CHUNK_SAMPLES):
        aligner.read(pcm(*playback[start : start + _CHUNK_SAMPLES]))
        confidences.append(aligner.echo_confidence)
        assert aligner.is_aligned or start < _CHUNK_SAMPLES

    # The pause is reported as no echo without costing the alignment.
    assert min(confidences) == 0.0
    assert aligner.echo_confidence > 0.9


def test_reports_no_playback_while_the_room_is_on_its_own(
    pcm: Callable[..., bytes],
) -> None:
    rng = np.random.default_rng(41)
    reference = _reference(
        rng.integers(-12_000, 12_001, 3 * _SAMPLE_RATE, dtype=np.int16)
    )
    aligner = _aligner(reference)
    unrelated = rng.integers(-12_000, 12_001, 3 * _CHUNK_SAMPLES, dtype=np.int16)

    for start in range(0, 3 * _CHUNK_SAMPLES, _CHUNK_SAMPLES):
        aligner.read(pcm(*unrelated[start : start + _CHUNK_SAMPLES]))

    assert aligner.echo_confidence < 0.5


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
