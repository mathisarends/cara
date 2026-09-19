import asyncio
import logging
from uuid import UUID

import pytest

from voice.audio import AudioPlayback
from voice.integrations import VoiceIntegration, VoiceIntegrationContext
from voice.integrations.notifier import VoiceIntegrationNotifier
from voice.lifecycle import AssistantTurnStarted, UserTurnStarted

_TURN_ID = UUID("00000000-0000-0000-0000-000000000001")


class _Recording(VoiceIntegration):
    def __init__(self, calls: list[str], name: str) -> None:
        self._calls = calls
        self._name = name

    async def prepare(self, context: VoiceIntegrationContext) -> None:
        self._calls.append(f"{self._name}:prepare")

    async def on_session_starting(self) -> None:
        self._calls.append(f"{self._name}:starting")

    async def on_user_turn_started(self) -> None:
        self._calls.append(f"{self._name}:user_turn")

    async def on_assistant_turn_started(self, turn_id: UUID) -> None:
        self._calls.append(f"{self._name}:assistant_turn")

    async def on_session_stopped(self) -> None:
        self._calls.append(f"{self._name}:stopped")


class _FailingCallback(_Recording):
    async def on_user_turn_started(self) -> None:
        raise RuntimeError("lights unreachable")


class _FailingPreparation(_Recording):
    async def prepare(self, context: VoiceIntegrationContext) -> None:
        raise RuntimeError("bridge unreachable")


class _SilentPlayback(AudioPlayback):
    async def play(self, audio: bytes) -> None:
        pass


_CONTEXT = VoiceIntegrationContext(audio_player=_SilentPlayback())


def test_forwards_events_in_order_and_isolates_failing_integrations(
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls: list[str] = []

    async def run() -> None:
        notifier = VoiceIntegrationNotifier(
            (_FailingCallback(calls, "a"), _Recording(calls, "b"))
        )
        await notifier.start(_CONTEXT)
        await notifier.on_lifecycle_event(UserTurnStarted(turn_id=_TURN_ID))
        await notifier.on_lifecycle_event(AssistantTurnStarted(turn_id=_TURN_ID))
        await notifier.stop()
        await notifier.stop()

    with caplog.at_level(logging.ERROR):
        asyncio.run(run())

    assert calls == [
        "a:prepare",
        "b:prepare",
        "a:starting",
        "b:starting",
        "b:user_turn",
        "a:assistant_turn",
        "b:assistant_turn",
        "a:stopped",
        "b:stopped",
    ]
    assert "_FailingCallback failed to handle UserTurnStarted" in caplog.text


def test_a_failed_preparation_raises_but_prepared_integrations_still_stop() -> None:
    calls: list[str] = []

    async def run() -> None:
        notifier = VoiceIntegrationNotifier(
            (_FailingPreparation(calls, "a"), _Recording(calls, "b"))
        )
        with pytest.raises(RuntimeError, match="bridge unreachable"):
            await notifier.start(_CONTEXT)
        await notifier.stop()

    asyncio.run(run())

    assert calls == ["b:prepare", "b:stopped"]
