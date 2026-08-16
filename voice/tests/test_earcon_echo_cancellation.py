import asyncio
import io
import wave
from collections.abc import AsyncIterator
from pathlib import Path

from voice.audio.output import AudioPlayer
from voice.audio.ports import AudioInput, AudioOutput
from voice.echo_cancellation import EchoCancellation, EchoCanceller
from voice.events.listener import Earcon, EarconPlayer

_SAMPLE_RATE = 16_000
_FRAMES = 160


class OneChunkInput(AudioInput):
    @property
    def sample_rate(self) -> int:
        return _SAMPLE_RATE

    @property
    def channels(self) -> int:
        return 1

    @property
    def is_active(self) -> bool:
        return True

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def stream_chunks(self) -> AsyncIterator[bytes]:
        yield bytes(_FRAMES * 2)


class RecordingOutput(AudioOutput):
    def __init__(self) -> None:
        self.chunks: list[bytes] = []

    @property
    def is_playing(self) -> bool:
        return False

    async def start(self, *, sample_rate: int, channels: int) -> None:
        assert sample_rate == 44_100
        assert channels == 2

    async def stop(self) -> None:
        pass

    async def play_chunk(self, chunk: bytes) -> None:
        self.chunks.append(chunk)

    async def clear_buffer(self) -> None:
        pass


class RecordingCanceller(EchoCanceller):
    def __init__(self) -> None:
        self.references: list[bytes] = []

    def process(self, near_end: bytes, far_end: bytes) -> bytes:
        self.references.append(far_end)
        return near_end


def _wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(44_100)
        audio.writeframes((1000).to_bytes(2, "little", signed=True) * 2 * 441)
    return buffer.getvalue()


def test_earcon_playback_is_available_as_mono_microphone_reference(
    tmp_path: Path,
) -> None:
    for earcon in Earcon:
        (tmp_path / f"{earcon}.wav").write_bytes(_wav())

    now = 0.0
    canceller = RecordingCanceller()
    input_device, output_device = EchoCancellation(
        canceller,
        sample_rate=_SAMPLE_RATE,
        alignment_margin_s=0,
        clock=lambda: now,
    ).wrap(OneChunkInput(), RecordingOutput())
    earcons = EarconPlayer(AudioPlayer(output_device), sounds_dir=tmp_path)

    async def run() -> None:
        nonlocal now
        await earcons.play(Earcon.WAKE)
        now = _FRAMES / _SAMPLE_RATE
        assert [chunk async for chunk in input_device.stream_chunks()]

    asyncio.run(run())

    assert canceller.references == [(1000).to_bytes(2, "little", signed=True) * _FRAMES]
