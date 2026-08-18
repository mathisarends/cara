import asyncio
import inspect

from voice import VoiceAgent
from voice.events import FollowUpCountdown, SessionStarted
from voice.events.bus import EventBus
from voice.observer import Observer, ObserverContext, _ObserverBridge


class _RecordingObserver(Observer):
    def __init__(self) -> None:
        self.events: list[str] = []

    async def on_agent_starting(self) -> None:
        self.events.append("started")

    async def on_user_inactivity_countdown(self, remaining_seconds: int) -> None:
        self.events.append(f"countdown:{remaining_seconds}")

    async def prepare(self, context: ObserverContext) -> None:
        self.events.append("prepared")


def test_bridge_notifies_all_voice_agent_observers() -> None:
    async def run() -> tuple[_RecordingObserver, _RecordingObserver]:
        event_bus = EventBus()
        first = _RecordingObserver()
        second = _RecordingObserver()
        bridge = _ObserverBridge(
            event_bus=event_bus,
            observers=(first, second),
        )
        bridge.setup()

        await bridge.prepare()
        await event_bus.dispatch(SessionStarted())
        await event_bus.dispatch(FollowUpCountdown(remaining_seconds=3))
        return first, second

    first, second = asyncio.run(run())

    assert first.events == ["prepared", "started", "countdown:3"]
    assert second.events == ["prepared", "started", "countdown:3"]


def test_voice_agent_exposes_observers_without_leaking_event_bus() -> None:
    parameters = inspect.signature(VoiceAgent).parameters

    assert "observers" in parameters
    assert "listener" not in parameters
    assert "listeners" not in parameters
    assert "event_bus" not in parameters


def test_voice_agent_exposes_start_and_stop_lifecycle() -> None:
    assert callable(VoiceAgent.start)
    assert callable(VoiceAgent.stop)
    assert not hasattr(VoiceAgent, "run")
    assert not hasattr(VoiceAgent, "close")
