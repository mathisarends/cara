import asyncio
import io
import wave
from pathlib import Path

from voice import Earcon, SoundObserver
from voice.audio import AudioBridge
from voice.audio.ports import AudioOutput
from voice.echo_cancellation import PlaybackReference, ReferenceTapOutput
from voice.events import WakeWordDetected
from voice.events.bus import EventBus
from voice.events.models import VoiceResourcesClosing
from voice.observer import ObserverBridge

_SAMPLE_RATE = 16_000
_FRAMES = 160


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

    reference = PlaybackReference(_SAMPLE_RATE)
    output_device = ReferenceTapOutput(RecordingOutput(), reference)
    event_bus = EventBus()
    AudioBridge(
        event_bus=event_bus,
        output_device=output_device,
    )
    observer = SoundObserver(sounds_dir=tmp_path)
    observer_bridge = ObserverBridge(
        event_bus=event_bus,
        observers=(observer,),
    )
    observer_bridge.setup()

    async def run() -> None:
        await observer_bridge.prepare()
        await event_bus.emit(
            WakeWordDetected(score=0.9, sequence=1, name="hey_mycroft")
        )
        await event_bus.emit(VoiceResourcesClosing())

    asyncio.run(run())

    assert reference.read(0, _FRAMES) == (
        (1000).to_bytes(2, "little", signed=True) * _FRAMES
    )
