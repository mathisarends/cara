import pytest

from gateway.features.voice.presentation.media import MediaFrame, MediaFrameKind


def test_media_frame_round_trip() -> None:
    frame = MediaFrame(MediaFrameKind.INPUT_PCM, 3, 41, 1_234, b"pcm")

    assert MediaFrame.decode(frame.encode()) == frame


def test_media_frame_rejects_mismatched_payload_length() -> None:
    frame = MediaFrame(MediaFrameKind.INPUT_PCM, 1, 1, 0, b"pcm").encode()

    with pytest.raises(ValueError, match="payload length"):
        MediaFrame.decode(frame[:-1])
