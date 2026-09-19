import asyncio
from collections.abc import Awaitable, Callable
from uuid import UUID

from hueify import GroupedLight, Room
from hueify.models import GroupArchetype, GroupMetadata, HueEvent

from voice.audio import AudioPlayback
from voice.integrations import VoiceIntegrationContext
from voice.integrations.hue import HueIntegration
from voice.integrations.notifier import VoiceIntegrationNotifier
from voice.lifecycle import (
    AssistantSpeechStarted,
    AssistantToolCompleted,
    AssistantToolStarted,
    AssistantTurnStarted,
    UserTurnStarted,
    VoiceConversationEnded,
    VoiceLifecycleEvent,
    WakeWordDetected,
)

_ROOM_ID = UUID("00000000-0000-0000-0000-000000000001")
_GROUPED_LIGHT_ID = UUID("00000000-0000-0000-0000-000000000002")
_TURN_ID = UUID("00000000-0000-0000-0000-000000000003")


class _RecordingRooms:
    def __init__(self) -> None:
        self.room = Room(
            id=_ROOM_ID,
            metadata=GroupMetadata(name="Test room", archetype=GroupArchetype.BEDROOM),
            services=[],
        )
        self.grouped_light_state = GroupedLight(
            id=_GROUPED_LIGHT_ID,
            on={"on": True},
            dimming={"brightness": 50},
            color_temperature={"mirek": 292},
        )
        self.changes: list[tuple[float, int | None, float]] = []

    async def find_by_name(self, name: str) -> Room:
        assert name == "Test room"
        return self.room

    async def grouped_light(self, room_id: UUID) -> GroupedLight:
        assert room_id == _ROOM_ID
        return self.grouped_light_state

    async def set_state(
        self,
        room_id: UUID,
        *,
        on: bool,
        brightness: float,
        mirek: int | None,
        transition: float,
    ) -> None:
        assert room_id == _ROOM_ID
        assert on is True
        self.changes.append((brightness, mirek, transition))


class _RecordingHue:
    def __init__(self) -> None:
        self.rooms = _RecordingRooms()
        self.stream_started = False
        self.closed = False
        self._handlers: dict[str, Callable[[HueEvent], Awaitable[object]]] = {}

    def on(
        self,
        event_type: str,
        handler: Callable[[HueEvent], Awaitable[object]],
    ) -> None:
        self._handlers[event_type] = handler

    def off(
        self,
        event_type: str,
        handler: Callable[[HueEvent], Awaitable[object]],
    ) -> None:
        assert self._handlers[event_type] == handler
        del self._handlers[event_type]

    async def start_stream(self) -> None:
        self.stream_started = True

    async def close(self) -> None:
        self.closed = True

    async def emit(self, event: HueEvent) -> None:
        await self._handlers["grouped_light"](event)


class _SilentPlayback(AudioPlayback):
    async def play(self, audio: bytes) -> None:
        pass


async def _start(
    hue: _RecordingHue,
) -> tuple[VoiceIntegrationNotifier, HueIntegration]:
    integration = HueIntegration(room_name="Test room", hue=hue)
    notifier = VoiceIntegrationNotifier((integration,))
    await notifier.start(VoiceIntegrationContext(audio_player=_SilentPlayback()))
    return notifier, integration


async def _dispatch_and_drain(
    notifier: VoiceIntegrationNotifier,
    integration: HueIntegration,
    event: VoiceLifecycleEvent,
) -> None:
    await notifier.on_lifecycle_event(event)
    await asyncio.wait_for(integration._jobs.join(), timeout=1)


def test_hue_integration_reflects_voice_turn_and_tool_lifecycle() -> None:
    async def run() -> _RecordingHue:
        hue = _RecordingHue()
        notifier, integration = await _start(hue)

        assert hue.rooms.changes == []
        await _dispatch_and_drain(
            notifier,
            integration,
            WakeWordDetected(score=0.9, sequence=1, name="hey_mycroft"),
        )
        await _dispatch_and_drain(
            notifier, integration, UserTurnStarted(turn_id=_TURN_ID)
        )
        await _dispatch_and_drain(
            notifier, integration, AssistantTurnStarted(turn_id=_TURN_ID)
        )
        await _dispatch_and_drain(
            notifier, integration, AssistantSpeechStarted(turn_id=_TURN_ID)
        )
        await _dispatch_and_drain(
            notifier,
            integration,
            AssistantToolStarted(turn_id=_TURN_ID, name="weather"),
        )
        await _dispatch_and_drain(
            notifier,
            integration,
            AssistantToolCompleted(turn_id=_TURN_ID, name="weather"),
        )
        await _dispatch_and_drain(
            notifier,
            integration,
            AssistantToolStarted(turn_id=_TURN_ID, name="calendar"),
        )
        await _dispatch_and_drain(
            notifier,
            integration,
            AssistantToolStarted(turn_id=_TURN_ID, name="mail"),
        )
        await _dispatch_and_drain(
            notifier,
            integration,
            AssistantToolCompleted(turn_id=_TURN_ID, name="calendar"),
        )
        await _dispatch_and_drain(
            notifier,
            integration,
            AssistantToolCompleted(turn_id=_TURN_ID, name="mail"),
        )
        await _dispatch_and_drain(
            notifier,
            integration,
            VoiceConversationEnded(reason="inactivity_timeout"),
        )
        await notifier.stop()
        return hue

    hue = asyncio.run(run())

    assert hue.stream_started is True
    assert hue.closed is True
    assert hue.rooms.changes == [
        (58.0, 275, 0.2),
        (47.0, 309, 0.4),
        (50.0, 292, 0.5),
    ]


def test_hue_integration_preserves_external_changes_in_its_baseline() -> None:
    async def run() -> list[tuple[float, int | None, float]]:
        hue = _RecordingHue()
        notifier, integration = await _start(hue)

        await _dispatch_and_drain(
            notifier, integration, UserTurnStarted(turn_id=_TURN_ID)
        )
        await hue.emit(
            HueEvent.model_validate(
                {
                    "id": _GROUPED_LIGHT_ID,
                    "type": "grouped_light",
                    "dimming": {"brightness": 75},
                    "color_temperature": {"mirek": 250},
                }
            )
        )
        await notifier.stop()
        return hue.rooms.changes

    assert asyncio.run(run()) == [(58.0, 275, 0.2), (67.0, 267, 0.5)]
