import numpy as np

from voice.echo_cancellation.alignment import ReferenceAligner
from voice.echo_cancellation.cancellers import NlmsEchoCanceller
from voice.echo_cancellation.reference import PlaybackReference

_SAMPLE_RATE = 16_000
_CHUNK_SAMPLES = 1_280


def test_unknown_network_delay_and_room_echo_are_cancelled() -> None:
    rng = np.random.default_rng(31)
    white = rng.normal(0, 0.12, 4 * _SAMPLE_RATE)
    playback = np.convolve(white, np.ones(6) / 6, mode="same")
    reference = PlaybackReference(_SAMPLE_RATE)
    reference.start_playback()
    reference.write(_pcm(playback))

    room = np.zeros(321)
    room[[40, 95, 210, 320]] = [0.55, 0.22, -0.13, 0.08]
    echo = np.convolve(playback, room)[: playback.size]
    network_delay = round(1.15 * _SAMPLE_RATE)
    microphone = np.concatenate((np.zeros(network_delay), echo))[: playback.size]

    aligner = ReferenceAligner(reference)
    canceller = NlmsEchoCanceller(_SAMPLE_RATE)
    cleaned = []
    for start in range(0, microphone.size, _CHUNK_SAMPLES):
        near = _pcm(microphone[start : start + _CHUNK_SAMPLES])
        cleaned.append(canceller.process(near, aligner.read(near)))

    actual = np.frombuffer(b"".join(cleaned), dtype="<i2").astype(np.float64)
    original = microphone[: actual.size] * 32_768
    final_second = slice(3 * _SAMPLE_RATE, 4 * _SAMPLE_RATE)
    attenuation_db = 20 * np.log10(
        (_rms(actual[final_second]) + 1e-12) / (_rms(original[final_second]) + 1e-12)
    )

    assert aligner.is_aligned
    assert attenuation_db < -20


def _pcm(samples: np.ndarray) -> bytes:
    return np.clip(samples * 32_768, -32_768, 32_767).astype("<i2").tobytes()


def _rms(samples: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(samples))))
