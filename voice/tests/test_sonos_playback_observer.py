import asyncio
import logging
from typing import cast

from sonosify import SonosClient, TransportInfo, TransportState

import voice.playback.sonos as sonos_module
from voice import SonosPlaybackObserver
from voice.events import (
    FollowUpTimedOut,
    SessionEnded,
    UserTurnStarted,
    WakeWordDetected,
)
from voice.events.bus import EventBus
from voice.observer import _ObserverBridge


class _RecordingSonosClient:
    def __init__(self, state: TransportState) -> None:
        self.ip = "192.0.2.1"
        self.state = state
        self.pause_calls = 0
        self.play_calls = 0
        self.closed = False

    async def get_transport_info(self) -> TransportInfo:
        return TransportInfo(CurrentTransportState=self.state)

    async def pause(self) -> None:
        self.pause_calls += 1
        self.state = TransportState.PAUSED_PLAYBACK

    async def play(self) -> None:
        self.play_calls += 1
        self.state = TransportState.PLAYING

    async def close(self) -> None:
        self.closed = True


def test_pauses_playback_for_interaction_and_resumes_after_timeout(caplog) -> None:
    caplog.set_level(logging.INFO, logger="voice.playback.sonos")

    async def run() -> _RecordingSonosClient:
        event_bus = EventBus()
        client = _RecordingSonosClient(TransportState.PLAYING)
        observer = SonosPlaybackObserver(client=cast(SonosClient, client))
        bridge = _ObserverBridge(event_bus=event_bus, observers=(observer,))
        bridge.setup()
        await bridge.prepare()

        await event_bus.dispatch(UserTurnStarted())
        await event_bus.dispatch(
            WakeWordDetected(name="hey_mycroft", score=0.9, sequence=2)
        )
        await event_bus.dispatch(FollowUpTimedOut(timeout_seconds=5))
        await event_bus.dispatch(SessionEnded())
        return client

    client = asyncio.run(run())

    assert client.pause_calls == 1
    assert client.play_calls == 1
    assert client.closed is False
    assert (
        "Sonos playback PLAYING -> PAUSED_PLAYBACK: user turn started"
        in caplog.messages
    )
    assert (
        "Sonos playback PAUSED_PLAYBACK -> PLAYING: user inactivity timeout"
        in caplog.messages
    )


def test_does_not_resume_playback_it_did_not_pause() -> None:
    async def run() -> _RecordingSonosClient:
        event_bus = EventBus()
        client = _RecordingSonosClient(TransportState.PAUSED_PLAYBACK)
        observer = SonosPlaybackObserver(client=cast(SonosClient, client))
        bridge = _ObserverBridge(event_bus=event_bus, observers=(observer,))
        bridge.setup()
        await bridge.prepare()

        await event_bus.dispatch(UserTurnStarted())
        await event_bus.dispatch(FollowUpTimedOut(timeout_seconds=5))
        return client

    client = asyncio.run(run())

    assert client.pause_calls == 0
    assert client.play_calls == 0


def test_loads_sonos_target_from_settings(monkeypatch) -> None:
    async def run() -> tuple[tuple[str | None, str | None], _RecordingSonosClient]:
        client = _RecordingSonosClient(TransportState.STOPPED)

        class RecordingController:
            call: tuple[str | None, str | None]

            async def client(
                self,
                room: str | None,
                *,
                ip: str | None,
            ) -> _RecordingSonosClient:
                self.call = (room, ip)
                return client

        controller = RecordingController()
        monkeypatch.setattr(sonos_module, "SonosController", lambda: controller)
        observer = SonosPlaybackObserver()
        event_bus = EventBus()
        bridge = _ObserverBridge(event_bus=event_bus, observers=(observer,))
        bridge.setup()

        await bridge.prepare()
        await event_bus.dispatch(SessionEnded())
        return controller.call, client

    monkeypatch.setenv("SONOS_SPEAKER_NAME", "Arbeitszimmer")
    monkeypatch.setenv("SONOS_IP_ADDRESS", "192.0.2.10")

    call, client = asyncio.run(run())

    assert call == ("Arbeitszimmer", "192.0.2.10")
    assert client.closed is True
