import asyncio
import io
import wave

from cara.audio import player as player_module
from cara.audio.player import WavAudioPlayer


class RecordingOutputStream:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.stopped = False
        self.closed = False

    def write(self, audio: bytes) -> None:
        self.writes.append(audio)

    def stop_stream(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True


class RecordingPyAudio:
    def __init__(self) -> None:
        self.stream = RecordingOutputStream()
        self.opened_with: dict[str, object] | None = None
        self.terminated = False

    def get_format_from_width(self, width: int) -> int:
        return width

    def open(self, **kwargs: object) -> RecordingOutputStream:
        self.opened_with = kwargs
        return self.stream

    def terminate(self) -> None:
        self.terminated = True


def _wav_audio(*, frames: bytes, frame_rate: int = 8000, channels: int = 1, sample_width: int = 2) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(sample_width)
        wav.setframerate(frame_rate)
        wav.writeframes(frames)
    return output.getvalue()


def test_wav_player_writes_trailing_silence_before_closing(monkeypatch) -> None:
    pa = RecordingPyAudio()
    monkeypatch.setattr(player_module.pyaudio, "PyAudio", lambda: pa)
    speech = b"\x01\x02" * 4

    WavAudioPlayer(trailing_silence_seconds=0.2)._play_sync(_wav_audio(frames=speech))

    assert pa.stream.writes == [speech, bytes(8000 * 2 // 5)]
    assert pa.stream.stopped is True
    assert pa.stream.closed is True
    assert pa.terminated is True


def test_wav_player_does_not_delay_cancelled_playback(monkeypatch) -> None:
    pa = RecordingPyAudio()
    monkeypatch.setattr(player_module.pyaudio, "PyAudio", lambda: pa)
    cancel = asyncio.Event()
    cancel.set()

    WavAudioPlayer()._play_sync(_wav_audio(frames=b"\x01\x02"), cancel=cancel)

    assert pa.stream.writes == []
