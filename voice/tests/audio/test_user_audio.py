import asyncio
from collections.abc import AsyncIterator

from voice.audio import AudioInput, BufferedAudioInput, UserAudioProducer
from voice.events import SessionStarted, UserAudioChunk
from voice.events.bus import EventBus
from voice.events.models import VoiceResourcesClosing


class _Input(AudioInput):
    def __init__(self) -> None:
        self._active = False
        self._chunks: asyncio.Queue[bytes] = asyncio.Queue()

    @property
    def sample_rate(self) -> int:
        return 16_000

    @property
    def channels(self) -> int:
        return 1

    @property
    def frames_per_chunk(self) -> int:
        return 1_280

    @property
    def is_active(self) -> bool:
        return self._active

    async def start(self) -> None:
        self._active = True

    async def stop(self) -> None:
        self._active = False

    async def stream_chunks(self) -> AsyncIterator[bytes]:
        while self._active:
            yield await self._chunks.get()

    async def send(self, chunk: bytes) -> None:
        await self._chunks.put(chunk)


def test_user_audio_is_published_without_an_active_turn() -> None:
    async def run() -> list[UserAudioChunk]:
        input_device = _Input()
        event_bus = EventBus()
        UserAudioProducer(
            event_bus=event_bus,
            buffered_audio_input=BufferedAudioInput(input_device),
        )
        received: list[UserAudioChunk] = []
        all_received = asyncio.Event()

        async def capture(event: UserAudioChunk) -> None:
            received.append(event)
            if len(received) == 3:
                all_received.set()

        event_bus.on(UserAudioChunk, capture)
        await event_bus.dispatch(SessionStarted())
        for chunk in (b"first", b"second", b"third"):
            await input_device.send(chunk)
        await asyncio.wait_for(all_received.wait(), timeout=1.0)
        await event_bus.dispatch(VoiceResourcesClosing())
        return received

    assert asyncio.run(run()) == [
        UserAudioChunk(sequence=0, chunk=b"first"),
        UserAudioChunk(sequence=1, chunk=b"second"),
        UserAudioChunk(sequence=2, chunk=b"third"),
    ]
