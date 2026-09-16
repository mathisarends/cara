import asyncio
import logging
from typing import cast

from sonosify import (
    AVTransportEvent,
    EventService,
    SonosClient,
    TransportInfo,
    TransportState,
)

import voice.playback.ducking as ducking_module
from voice import (
    SonosAudioFocusObserver,
    SonosDuckingPolicy,
    SonosPausePolicy,
)
from voice.events import (
    FollowUpTimedOut,
    SessionEnded,
    UserTurnStarted,
    WakeWordDetected,
)
from voice.events.bus import EventBus
from voice.observer import ObserverBridge


class _RecordingSonosClient:
    def __init__(self, state: TransportState) -> None:
        self.ip = "192.0.2.1"
        self.state = state
        self.duck_calls: list[int | None] = []
        self.unduck_calls = 0
        self.pause_calls = 0
        self.play_calls = 0
        self.duck_refreshed = asyncio.Event()
        self.subscription = _RecordingEventSubscription()
        self.watched_services: tuple[EventService, ...] | None = None
        self.closed = False

    async def get_transport_info(self) -> TransportInfo:
        return TransportInfo(CurrentTransportState=self.state)

    async def duck(self, duration_millis: int | None = None) -> None:
        self.duck_calls.append(duration_millis)
        if len(self.duck_calls) > 1:
            self.duck_refreshed.set()

    async def unduck(self) -> None:
        self.unduck_calls += 1

    async def pause(self) -> None:
        self.pause_calls += 1
        self.state = TransportState.PAUSED_PLAYBACK

    async def play(self) -> None:
        self.play_calls += 1
        self.state = TransportState.PLAYING

    def watch(
        self, *, services: tuple[EventService, ...]
    ) -> "_RecordingEventSubscription":
        self.watched_services = services
        return self.subscription

    async def close(self) -> None:
        self.closed = True


class _RecordingEventSubscription:
    def __init__(self) -> None:
        self._events: asyncio.Queue[AVTransportEvent] = asyncio.Queue()
        self.started = False
        self.closed = False

    def __aiter__(self) -> "_RecordingEventSubscription":
        return self

    async def __anext__(self) -> AVTransportEvent:
        return await self._events.get()

    async def start(self) -> None:
        self.started = True

    async def close(self) -> None:
        self.closed = True

    async def emit(self, state: TransportState) -> None:
        await self._events.put(AVTransportEvent(TransportState=state))


def test_ducks_playback_for_interaction_and_unducks_after_timeout(caplog) -> None:
    caplog.set_level(logging.INFO, logger="voice.playback.ducking")

    async def run() -> _RecordingSonosClient:
        event_bus = EventBus()
        client = _RecordingSonosClient(TransportState.PLAYING)
        observer = SonosAudioFocusObserver(
            policy=SonosDuckingPolicy(client=cast(SonosClient, client))
        )
        bridge = ObserverBridge(event_bus=event_bus, observers=(observer,))
        bridge.setup()
        await bridge.prepare()

        await event_bus.emit(UserTurnStarted())
        await event_bus.emit(
            WakeWordDetected(name="hey_mycroft", score=0.9, sequence=2)
        )
        await event_bus.emit(FollowUpTimedOut(timeout_seconds=5))
        await event_bus.emit(SessionEnded())
        return client

    client = asyncio.run(run())

    assert client.duck_calls == [60_000]
    assert client.unduck_calls == 1
    assert client.closed is False
    assert (
        "Sonos playback ducked for up to 60 seconds: user turn started"
        in caplog.messages
    )
    assert "Sonos playback unducked: user inactivity timeout" in caplog.messages


def test_does_not_unduck_playback_it_did_not_duck() -> None:
    async def run() -> _RecordingSonosClient:
        event_bus = EventBus()
        client = _RecordingSonosClient(TransportState.PAUSED_PLAYBACK)
        observer = SonosAudioFocusObserver(
            policy=SonosDuckingPolicy(client=cast(SonosClient, client))
        )
        bridge = ObserverBridge(event_bus=event_bus, observers=(observer,))
        bridge.setup()
        await bridge.prepare()

        await event_bus.emit(UserTurnStarted())
        await event_bus.emit(FollowUpTimedOut(timeout_seconds=5))
        return client

    client = asyncio.run(run())

    assert client.duck_calls == []
    assert client.unduck_calls == 0


def test_refreshes_duck_until_interaction_ends(monkeypatch) -> None:
    async def run() -> _RecordingSonosClient:
        client = _RecordingSonosClient(TransportState.PLAYING)
        observer = SonosAudioFocusObserver(
            policy=SonosDuckingPolicy(client=cast(SonosClient, client))
        )
        event_bus = EventBus()
        bridge = ObserverBridge(event_bus=event_bus, observers=(observer,))
        bridge.setup()
        await bridge.prepare()

        await event_bus.emit(UserTurnStarted())
        await asyncio.wait_for(client.duck_refreshed.wait(), timeout=1)
        await event_bus.emit(FollowUpTimedOut(timeout_seconds=5))
        return client

    monkeypatch.setattr(ducking_module, "_DUCK_REFRESH_SECONDS", 0.01)

    client = asyncio.run(run())

    assert len(client.duck_calls) >= 2
    assert set(client.duck_calls) == {60_000}
    assert client.unduck_calls == 1


def test_can_use_pause_policy() -> None:
    async def run() -> _RecordingSonosClient:
        client = _RecordingSonosClient(TransportState.PLAYING)
        observer = SonosAudioFocusObserver(
            policy=SonosPausePolicy(client=cast(SonosClient, client)),
        )
        event_bus = EventBus()
        bridge = ObserverBridge(event_bus=event_bus, observers=(observer,))
        bridge.setup()
        await bridge.prepare()

        await event_bus.emit(UserTurnStarted())
        await event_bus.emit(FollowUpTimedOut(timeout_seconds=5))
        return client

    client = asyncio.run(run())

    assert client.pause_calls == 1
    assert client.play_calls == 1
    assert client.duck_calls == []
    assert client.watched_services == (EventService.AV_TRANSPORT,)
    assert client.subscription.started is True
    assert client.subscription.closed is True


def test_pause_policy_does_not_resume_after_external_pause() -> None:
    async def run() -> _RecordingSonosClient:
        client = _RecordingSonosClient(TransportState.PLAYING)
        observer = SonosAudioFocusObserver(
            policy=SonosPausePolicy(client=cast(SonosClient, client)),
        )
        event_bus = EventBus()
        bridge = ObserverBridge(event_bus=event_bus, observers=(observer,))
        bridge.setup()
        await bridge.prepare()

        await event_bus.emit(UserTurnStarted())
        await client.subscription.emit(TransportState.PAUSED_PLAYBACK)
        await asyncio.sleep(0)
        await client.subscription.emit(TransportState.PAUSED_PLAYBACK)
        await asyncio.sleep(0)
        await event_bus.emit(FollowUpTimedOut(timeout_seconds=5))
        return client

    client = asyncio.run(run())

    assert client.pause_calls == 1
    assert client.play_calls == 0
    assert client.subscription.closed is True
