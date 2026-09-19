import asyncio
import inspect

from voice import VoiceChannel
from voice.events import (
    SessionStarted,
    VoiceConversationEnded,
    VoiceConversationInactivityCountdown,
)
from voice.events.bus import EventBus
from voice.integrations import VoiceIntegration, VoiceIntegrationContext
from voice.integrations.bridge import VoiceIntegrationBridge


class _RecordingVoiceIntegration(VoiceIntegration):
    def __init__(self) -> None:
        self.events: list[str] = []

    async def on_channel_starting(self) -> None:
        self.events.append("started")

    async def on_voice_conversation_inactivity_countdown(
        self, remaining_seconds: int
    ) -> None:
        self.events.append(f"countdown:{remaining_seconds}")

    async def on_voice_conversation_ended(self, reason: str) -> None:
        self.events.append(f"ended:{reason}")

    async def prepare(self, context: VoiceIntegrationContext) -> None:
        self.events.append("prepared")


def test_bridge_notifies_all_voice_channel_integrations() -> None:
    async def run() -> tuple[_RecordingVoiceIntegration, _RecordingVoiceIntegration]:
        event_bus = EventBus()
        first = _RecordingVoiceIntegration()
        second = _RecordingVoiceIntegration()
        bridge = VoiceIntegrationBridge(
            event_bus=event_bus,
            integrations=(first, second),
        )
        bridge.setup()

        await bridge.prepare()
        await event_bus.emit(SessionStarted())
        await event_bus.emit(VoiceConversationInactivityCountdown(remaining_seconds=3))
        await event_bus.emit(VoiceConversationEnded(reason="inactivity_timeout"))
        return first, second

    first, second = asyncio.run(run())

    assert first.events == [
        "prepared",
        "started",
        "countdown:3",
        "ended:inactivity_timeout",
    ]
    assert second.events == first.events


def test_voice_channel_exposes_integrations_without_leaking_event_bus() -> None:
    parameters = inspect.signature(VoiceChannel).parameters

    assert "integrations" in parameters
    assert "listener" not in parameters
    assert "listeners" not in parameters
    assert "event_bus" not in parameters


def test_voice_channel_exposes_start_and_stop_lifecycle() -> None:
    assert callable(VoiceChannel.start)
    assert callable(VoiceChannel.stop)
    assert not hasattr(VoiceChannel, "run")
    assert not hasattr(VoiceChannel, "close")
