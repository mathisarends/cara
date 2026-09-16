import asyncio
from uuid import uuid4

from voice.activation import ActivationKind
from voice.events import (
    AssistantPlaybackCompleted,
    FollowUpTimedOut,
    UserSpeechStarted,
    VoiceTurnTimedOut,
)
from voice.events.bus import EventBus
from voice.events.models import VoiceTurnEnded, VoiceTurnRequested
from voice.handler import FollowUpHandler, FollowUpSettings


def test_follow_up_settings_use_expected_defaults() -> None:
    settings = FollowUpSettings()

    assert settings.window_seconds == 5.0
    assert settings.countdown_seconds == 3


def test_finished_response_requests_a_gateway_follow_up_turn() -> None:
    async def run() -> VoiceTurnRequested:
        event_bus = EventBus()
        FollowUpHandler(event_bus=event_bus)
        requested = asyncio.get_running_loop().create_future()

        async def capture(event: VoiceTurnRequested) -> None:
            requested.set_result(event)

        event_bus.on_request(VoiceTurnRequested, capture)
        turn_id = uuid4()
        await event_bus.emit(AssistantPlaybackCompleted(turn_id=turn_id))
        await event_bus.emit(VoiceTurnEnded(turn_id=turn_id))
        return await requested

    request = asyncio.run(run())

    assert request.activation is ActivationKind.FOLLOW_UP
    assert request.speech_start_timeout == 5.0


def test_gateway_timeout_closes_the_follow_up_window() -> None:
    async def run() -> FollowUpTimedOut:
        event_bus = EventBus()
        handler = FollowUpHandler(
            event_bus=event_bus,
            settings=FollowUpSettings(window_seconds=1.0, countdown_seconds=0),
        )
        event_bus.on_request(VoiceTurnRequested, _no_op_request_handler)
        timed_out = asyncio.get_running_loop().create_future()

        async def capture(event: FollowUpTimedOut) -> None:
            timed_out.set_result(event)

        event_bus.on(FollowUpTimedOut, capture)
        turn_id = uuid4()
        await event_bus.emit(AssistantPlaybackCompleted(turn_id=turn_id))
        await event_bus.emit(VoiceTurnEnded(turn_id=turn_id))
        await event_bus.emit(VoiceTurnTimedOut(turn_id=uuid4()))
        result = await timed_out
        handler.close()
        return result

    assert asyncio.run(run()).timeout_seconds == 1.0


def test_user_speech_closes_the_follow_up_window() -> None:
    async def run() -> list[FollowUpTimedOut]:
        event_bus = EventBus()
        handler = FollowUpHandler(event_bus=event_bus)
        event_bus.on_request(VoiceTurnRequested, _no_op_request_handler)
        timed_out: list[FollowUpTimedOut] = []

        async def capture(event: FollowUpTimedOut) -> None:
            timed_out.append(event)

        event_bus.on(FollowUpTimedOut, capture)
        turn_id = uuid4()
        await event_bus.emit(AssistantPlaybackCompleted(turn_id=turn_id))
        await event_bus.emit(VoiceTurnEnded(turn_id=turn_id))
        await event_bus.emit(UserSpeechStarted())
        await event_bus.emit(VoiceTurnTimedOut(turn_id=uuid4()))
        handler.close()
        return timed_out

    assert asyncio.run(run()) == []


async def _no_op_request_handler(_: VoiceTurnRequested) -> None:
    return None
