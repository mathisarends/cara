import asyncio
from uuid import uuid4

from voice.events import (
    AssistantResponseStarted,
    AudioPlaybackRequested,
    SessionEnded,
    WakeWordDetected,
)
from voice.events.bus import EventBus
from voice.observer import ObserverBridge
from voice.sound import _DEFAULT_SOUNDS_DIR, Earcon, SoundObserver


def test_wake_word_detected_plays_wake_earcon_before_dispatch_completes() -> None:
    async def run() -> list[bytes]:
        event_bus = EventBus()
        requested: list[bytes] = []

        async def capture(request: AudioPlaybackRequested) -> None:
            requested.append(request.audio)

        event_bus.on_request(AudioPlaybackRequested, capture)
        observer = SoundObserver()
        bridge = ObserverBridge(
            event_bus=event_bus,
            observers=(observer,),
        )
        bridge.setup()
        await bridge.prepare()
        await event_bus.emit(
            WakeWordDetected(score=0.8, sequence=4, name="hey_mycroft")
        )
        return requested

    assert asyncio.run(run()) == [
        (_DEFAULT_SOUNDS_DIR / f"{Earcon.WAKE}.wav").read_bytes()
    ]


def test_session_ended_plays_sleep_earcon_before_dispatch_completes() -> None:
    async def run() -> list[bytes]:
        event_bus = EventBus()
        requested: list[bytes] = []

        async def capture(request: AudioPlaybackRequested) -> None:
            requested.append(request.audio)

        event_bus.on_request(AudioPlaybackRequested, capture)
        observer = SoundObserver()
        bridge = ObserverBridge(
            event_bus=event_bus,
            observers=(observer,),
        )
        bridge.setup()
        await bridge.prepare()
        await event_bus.emit(SessionEnded())
        return requested

    assert asyncio.run(run()) == [
        (_DEFAULT_SOUNDS_DIR / f"{Earcon.SLEEP}.wav").read_bytes()
    ]


def test_assistant_response_started_plays_success_earcon() -> None:
    async def run() -> list[bytes]:
        event_bus = EventBus()
        requested: list[bytes] = []

        async def capture(request: AudioPlaybackRequested) -> None:
            requested.append(request.audio)

        event_bus.on_request(AudioPlaybackRequested, capture)
        observer = SoundObserver()
        bridge = ObserverBridge(
            event_bus=event_bus,
            observers=(observer,),
        )
        bridge.setup()
        await bridge.prepare()
        await event_bus.emit(AssistantResponseStarted(turn_id=uuid4()))
        return requested

    assert asyncio.run(run()) == [
        (_DEFAULT_SOUNDS_DIR / f"{Earcon.SUCCESS}.wav").read_bytes()
    ]
