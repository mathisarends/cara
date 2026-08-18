import asyncio
import io
import wave
from collections.abc import AsyncIterator
from pathlib import Path

from voice.audio import AudioBridge, AudioHub
from voice.audio.ports import AudioInput, AudioOutput
from voice.echo_cancellation import (
    EchoCancellationSettings,
    EchoCanceller,
    wrap_with_echo_cancellation,
)
from voice.events import WakeWordDetected
from voice.events.bus import EventBus
from voice.events.listener import Earcon, SoundListener
from voice.events.models import VoiceResourcesClosing

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
    def frames_per_chunk(self) -> int:
        return _FRAMES

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
    input_device, output_device = wrap_with_echo_cancellation(
        OneChunkInput(),
        RecordingOutput(),
        canceller,
        settings=EchoCancellationSettings(
            sample_rate=_SAMPLE_RATE,
            alignment_margin_s=0,
            clock=lambda: now,
        ),
    )
    event_bus = EventBus()
    AudioBridge(
        event_bus=event_bus,
        audio_hub=AudioHub(input_device),
        output_device=output_device,
    )
    SoundListener(event_bus, sounds_dir=tmp_path)

    async def run() -> None:
        nonlocal now
        await event_bus.dispatch(
            WakeWordDetected(score=0.9, sequence=1, name="hey_mycroft")
        )
        now = _FRAMES / _SAMPLE_RATE
        assert [chunk async for chunk in input_device.stream_chunks()]
        await event_bus.dispatch(VoiceResourcesClosing())

    asyncio.run(run())

    assert canceller.references == [(1000).to_bytes(2, "little", signed=True) * _FRAMES]
