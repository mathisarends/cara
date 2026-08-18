import asyncio
import io
import wave

from voice.audio.output import AudioPlayer
from voice.audio.ports import AudioOutput


class RecordingOutput(AudioOutput):
    def __init__(self) -> None:
        self.started_with: tuple[int, int] | None = None
        self.chunks: list[bytes] = []
        self.stopped = False
        self.cleared = False
        self.finished = False

    @property
    def is_playing(self) -> bool:
        return bool(self.chunks) and not self.finished

    async def start(self, *, sample_rate: int, channels: int) -> None:
        self.started_with = (sample_rate, channels)

    async def stop(self) -> None:
        self.stopped = True

    async def play_chunk(self, chunk: bytes) -> None:
        self.chunks.append(chunk)

    async def finish_response(self) -> None:
        self.finished = True

    async def clear_buffer(self) -> None:
        self.cleared = True


def _wav(pcm: bytes, *, sample_rate: int = 16_000, channels: int = 1) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)
    return buffer.getvalue()


def test_audio_player_delegates_to_output() -> None:
    async def run() -> RecordingOutput:
        output = RecordingOutput()
        player = AudioPlayer(output)

        await player.play(_wav(b"\x01\x00\x02\x00"))

        return output

    output = asyncio.run(run())

    assert output.started_with == (16_000, 1)
    assert b"".join(output.chunks) == b"\x01\x00\x02\x00"
    assert output.finished is True


def test_audio_player_stops_output() -> None:
    async def run() -> bool:
        output = RecordingOutput()
        player = AudioPlayer(output)

        await player.stop()

        return output.stopped

    assert asyncio.run(run()) is True
