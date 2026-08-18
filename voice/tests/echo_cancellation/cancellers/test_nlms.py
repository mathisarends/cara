from collections.abc import Callable

import numpy as np

from voice.echo_cancellation.cancellers.nlms import NlmsEchoCanceller


def test_buffers_incomplete_blocks(pcm: Callable[..., bytes]) -> None:
    canceller = NlmsEchoCanceller(block_size=4)

    assert canceller.process(pcm(100, 200), pcm(0, 0)) == b""
    assert canceller.process(pcm(300, 400), pcm(0, 0)) == pcm(100, 200, 300, 400)


def test_silent_reference_preserves_near_end_audio(pcm: Callable[..., bytes]) -> None:
    canceller = NlmsEchoCanceller(block_size=4)
    near = pcm(-32_768, -1_000, 1_000, 32_767)

    assert canceller.process(near, pcm(0, 0, 0, 0)) == near


def test_adapts_to_a_far_end_signal_and_can_reset(pcm: Callable[..., bytes]) -> None:
    canceller = NlmsEchoCanceller(
        sample_rate=8,
        tail_ms=1_000,
        block_size=4,
        residual_leakage=0.2,
    )
    far = pcm(2_000, -2_000, 1_000, -1_000)
    near = pcm(1_000, -1_000, 500, -500)

    first = canceller.process(near, far)
    second = canceller.process(near, far)
    canceller.reset()
    after_reset = canceller.process(near, far)

    assert len(first) == len(near)
    assert len(second) == len(near)
    assert after_reset == first


def test_can_disable_residual_suppression(pcm: Callable[..., bytes]) -> None:
    canceller = NlmsEchoCanceller(block_size=4, residual_leakage=0)
    near = pcm(1_000, 2_000, 3_000, 4_000)
    far = pcm(500, 500, 500, 500)

    assert canceller.process(near, far) == near


def test_diverging_filter_is_reduced_before_adaptation() -> None:
    canceller = NlmsEchoCanceller(block_size=4)
    canceller._weights.fill(2)
    history = np.ones_like(canceller._weights)
    spectrum = np.ones(canceller._bins)
    residual_spectrum = np.ones(canceller._bins)

    canceller._adapt(
        history,
        spectrum,
        residual_spectrum,
        np.ones(4),
        np.full(4, 3.0),
    )

    np.testing.assert_array_equal(canceller._weights, np.ones_like(canceller._weights))
