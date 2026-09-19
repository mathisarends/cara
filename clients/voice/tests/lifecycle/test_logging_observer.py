import asyncio
import logging

from voice.lifecycle import (
    SessionStarted,
    VoiceConversationEnded,
    VoiceConversationInactivityCountdown,
)
from voice.lifecycle.logging_observer import LoggingObserver

_LOGGER = "voice.lifecycle.logging_observer"


def test_session_start_logs_configured_wake_word(caplog) -> None:
    async def run() -> None:
        observer = LoggingObserver(wake_word_phrase="hey jarvis")
        await observer.on_lifecycle_event(SessionStarted())

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        asyncio.run(run())

    assert 'Listening for "Hey Jarvis". Press Ctrl+C to quit.' in caplog.messages


def test_conversation_inactivity_countdown_is_logged(caplog) -> None:
    async def run() -> None:
        observer = LoggingObserver(wake_word_phrase="hey mycroft")
        for remaining in range(5, 0, -1):
            await observer.on_lifecycle_event(
                VoiceConversationInactivityCountdown(remaining_seconds=remaining)
            )

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        asyncio.run(run())

    assert caplog.messages == [
        "Voice conversation timeout in 5",
        "Voice conversation timeout in 4",
        "Voice conversation timeout in 3",
        "Voice conversation timeout in 2",
        "Voice conversation timeout in 1",
    ]


def test_wake_word_readiness_is_logged_after_conversation_ends(caplog) -> None:
    async def run() -> None:
        observer = LoggingObserver(wake_word_phrase="hey mycroft")
        await observer.on_lifecycle_event(
            VoiceConversationEnded(reason="inactivity_timeout")
        )

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        asyncio.run(run())

    assert caplog.messages == ['Listening for "Hey Mycroft". Press Ctrl+C to quit.']
