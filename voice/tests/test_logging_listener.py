import asyncio
import logging

from voice.events import (
    FollowUpCountdown,
    FollowUpTimedOut,
    SessionStarted,
)
from voice.events.bus import EventBus
from voice.events.listener import LoggingListener
from voice.events.models import VoiceTurnEnded

_LOGGER = "voice.events.listener.logging_listener"


def test_session_start_logs_configured_wake_word(caplog) -> None:
    async def run() -> None:
        event_bus = EventBus()
        LoggingListener(event_bus, wake_word_phrase="hey jarvis")
        await event_bus.dispatch(SessionStarted())

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        asyncio.run(run())

    assert 'Listening for "Hey Jarvis". Press Ctrl+C to quit.' in caplog.messages


def test_follow_up_countdown_is_logged(caplog) -> None:
    async def run() -> None:
        event_bus = EventBus()
        LoggingListener(event_bus, wake_word_phrase="hey mycroft")
        for remaining in range(5, 0, -1):
            await event_bus.dispatch(FollowUpCountdown(remaining_seconds=remaining))

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        asyncio.run(run())

    assert caplog.messages == [
        "Follow-up timeout in 5",
        "Follow-up timeout in 4",
        "Follow-up timeout in 3",
        "Follow-up timeout in 2",
        "Follow-up timeout in 1",
    ]


def test_wake_word_readiness_is_logged_after_timed_out_turn_ends(caplog) -> None:
    async def run() -> None:
        event_bus = EventBus()
        LoggingListener(event_bus, wake_word_phrase="hey mycroft")
        await event_bus.dispatch(FollowUpTimedOut(timeout_seconds=10.0))
        await event_bus.dispatch(VoiceTurnEnded(turn_id=2))

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        asyncio.run(run())

    assert caplog.messages == ['Listening for "Hey Mycroft". Press Ctrl+C to quit.']
