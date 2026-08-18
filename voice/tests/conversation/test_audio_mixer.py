import wave
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

from voice.conversation import ConversationAudioMixer


@pytest.mark.parametrize("sample_rate", [0, -1])
def test_rejects_non_positive_sample_rates(tmp_path: Path, sample_rate: int) -> None:
    with pytest.raises(ValueError, match="sample rates must be positive"):
        ConversationAudioMixer(tmp_path / "recording.wav", user_sample_rate=sample_rate)


def test_rejects_incomplete_pcm_frames(tmp_path: Path) -> None:
    mixer = ConversationAudioMixer(tmp_path / "recording.wav")

    with pytest.raises(ValueError, match="complete 16-bit samples"):
        mixer.feed_user(b"\x00")


def test_empty_recording_does_not_create_a_file(tmp_path: Path) -> None:
    path = tmp_path / "recording.wav"
    mixer = ConversationAudioMixer(path)

    mixer.feed_user(b"")
    mixer.feed_assistant(b"")
    mixer.save()

    assert mixer.path == path
    assert not path.exists()


def test_mixes_timestamped_tracks_and_clips_overflow(
    tmp_path: Path, pcm: Callable[..., bytes]
) -> None:
    times = iter([10.0, 10.5])
    path = tmp_path / "nested" / "recording.wav"
    mixer = ConversationAudioMixer(
        path,
        user_sample_rate=2,
        assistant_sample_rate=2,
        output_sample_rate=2,
        clock=lambda: next(times),
    )

    mixer.feed_user(pcm(30_000, 30_000))
    mixer.feed_assistant(pcm(10_000, -2_000))
    mixer.save()

    with wave.open(str(path), "rb") as recording:
        assert recording.getparams()[:4] == (1, 2, 2, 3)
        samples = np.frombuffer(recording.readframes(3), dtype="<i2")

    np.testing.assert_array_equal(samples, [30_000, 32_767, -2_000])


def test_resamples_input_to_the_output_rate(
    tmp_path: Path, pcm: Callable[..., bytes]
) -> None:
    path = tmp_path / "recording.wav"
    mixer = ConversationAudioMixer(
        path,
        user_sample_rate=2,
        assistant_sample_rate=4,
        output_sample_rate=4,
        clock=lambda: 0.0,
    )

    mixer.feed_user(pcm(0, 1_000))
    mixer.save()

    with wave.open(str(path), "rb") as recording:
        samples = np.frombuffer(recording.readframes(4), dtype="<i2")

    np.testing.assert_array_equal(samples, [0, 500, 1_000, 1_000])
