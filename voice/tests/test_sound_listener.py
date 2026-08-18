import asyncio

from voice.events import AudioPlaybackRequested, SessionEnded, WakeWordDetected
from voice.events.bus import EventBus
from voice.events.listener import Earcon, SoundListener
from voice.events.listener.sound_listener import _DEFAULT_SOUNDS_DIR


def test_wake_word_detected_plays_wake_earcon_before_dispatch_completes() -> None:
    async def run() -> list[bytes]:
        event_bus = EventBus()
        requested: list[bytes] = []

        async def capture(event: AudioPlaybackRequested) -> None:
            requested.append(event.audio)

        event_bus.on_request(AudioPlaybackRequested, capture)
        SoundListener(event_bus)
        await event_bus.dispatch(
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

        async def capture(event: AudioPlaybackRequested) -> None:
            requested.append(event.audio)

        event_bus.on_request(AudioPlaybackRequested, capture)
        SoundListener(event_bus)
        await event_bus.dispatch(SessionEnded())
        return requested

    assert asyncio.run(run()) == [
        (_DEFAULT_SOUNDS_DIR / f"{Earcon.SLEEP}.wav").read_bytes()
    ]
