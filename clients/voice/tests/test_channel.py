import asyncio
from collections.abc import AsyncIterator
from typing import cast
from uuid import uuid4

import pytest

import voice.channel as channel_module
from voice import (
    ActivationSource,
    ExternalActivationSource,
    VoiceChannel,
    VoiceIntegration,
    VoiceIntegrationContext,
)
from voice.audio import AudioInput, AudioOutput
from voice.barge_in import BargeInContext, BargeInSignal, BargeInStrategy
from voice.events import AssistantTurnStarted
from voice.events.bus import EventBus
from voice.events.models import VoiceTurnEnded
from voice.gateway import GatewayVoiceSession
from voice.wakeword import WakeWordDetection


class _WakeWordListener:
    phrase = "hey mycroft"

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def detections(self) -> AsyncIterator[WakeWordDetection]:
        if False:
            yield WakeWordDetection(sequence=0, score=0, name="")


class _GatewaySession:
    input_sample_rate = 16_000
    output_sample_rate = 24_000
    output_channels = 1

    def __init__(self) -> None:
        self.closed = False

    @property
    def active_turn(self) -> None:
        return None

    async def voice_events(self) -> AsyncIterator[object]:
        await asyncio.Event().wait()
        yield

    async def media_frames(self) -> AsyncIterator[object]:
        await asyncio.Event().wait()
        yield

    async def close(self) -> None:
        self.closed = True


class _IdleWakeWordListener(_WakeWordListener):
    async def detections(self) -> AsyncIterator[WakeWordDetection]:
        await asyncio.Event().wait()
        yield WakeWordDetection(sequence=0, score=0, name="")


class _ManualBargeIn(BargeInStrategy):
    def __init__(self) -> None:
        self._signals: asyncio.Queue[BargeInSignal] = asyncio.Queue()

    def set_context(self, context: BargeInContext) -> None:
        pass

    def signal(self, sequence: int) -> None:
        self._signals.put_nowait(BargeInSignal(sequence=sequence))

    async def signals(self) -> AsyncIterator[BargeInSignal]:
        while True:
            yield await self._signals.get()


class _GatewayBridge:
    created: "_GatewayBridge"

    def __init__(
        self,
        event_bus: EventBus,
        *args: object,
        max_echo_confidence: float = 0.5,
    ) -> None:
        self.event_bus = event_bus
        self.max_echo_confidence = max_echo_confidence
        self.interrupts: list[int] = []
        _GatewayBridge.created = self

    async def start(self) -> None:
        pass

    async def interrupt(self, sequence: int) -> None:
        self.interrupts.append(sequence)


class _LifecycleVoiceIntegration(VoiceIntegration):
    def __init__(self) -> None:
        self.events: list[str] = []

    async def prepare(self, context: VoiceIntegrationContext) -> None:
        self.events.append("prepared")

    async def on_channel_starting(self) -> None:
        self.events.append("started")

    async def on_channel_stopped(self) -> None:
        self.events.append("stopped")


def test_runs_and_closes_an_injected_voice_stack(
    monkeypatch,
    audio_input: AudioInput,
    audio_output: AudioOutput,
) -> None:
    integration = _LifecycleVoiceIntegration()
    gateway_session = _GatewaySession()
    monkeypatch.setattr(channel_module, "WakeWordListener", _WakeWordListener)
    voice_channel = VoiceChannel(
        gateway_session=cast(GatewayVoiceSession, gateway_session),
        audio_input=audio_input,
        audio_output=audio_output,
        integrations=(integration,),
    )

    asyncio.run(voice_channel.start())
    asyncio.run(voice_channel.stop())

    assert gateway_session.closed
    assert integration.events == ["prepared", "started", "stopped"]

    with pytest.raises(RuntimeError, match="Voice channel is stopped"):
        asyncio.run(voice_channel.start())


def test_barge_in_interrupts_only_while_the_assistant_responds(
    monkeypatch,
    audio_input: AudioInput,
    audio_output: AudioOutput,
) -> None:
    monkeypatch.setattr(channel_module, "WakeWordListener", _IdleWakeWordListener)
    monkeypatch.setattr(channel_module, "GatewayVoiceBridge", _GatewayBridge)
    barge_in = _ManualBargeIn()
    voice_channel = VoiceChannel(
        gateway_session=cast(GatewayVoiceSession, _GatewaySession()),
        audio_input=audio_input,
        audio_output=audio_output,
        barge_in=barge_in,
    )
    bridge = _GatewayBridge.created

    async def scenario() -> None:
        running = asyncio.create_task(voice_channel.start())
        await _settle()
        barge_in.signal(1)
        await _settle()
        assert bridge.interrupts == []

        await bridge.event_bus.emit(AssistantTurnStarted())
        barge_in.signal(2)
        barge_in.signal(3)
        await _settle()
        assert bridge.interrupts == [2]

        await bridge.event_bus.emit(AssistantTurnStarted())
        await bridge.event_bus.emit(VoiceTurnEnded(turn_id=uuid4()))
        barge_in.signal(4)
        await _settle()
        assert bridge.interrupts == [2]

        running.cancel()
        await asyncio.gather(running, return_exceptions=True)

    asyncio.run(scenario())


def test_configures_only_explicit_activation_sources(
    monkeypatch,
    audio_input: AudioInput,
    audio_output: AudioOutput,
) -> None:
    configured_sources: tuple[ActivationSource, ...] = ()
    activation_coordinator = channel_module.ActivationCoordinator

    def create_activation_coordinator(*, event_bus, sources):
        nonlocal configured_sources
        configured_sources = tuple(sources)
        return activation_coordinator(event_bus=event_bus, sources=configured_sources)

    monkeypatch.setattr(channel_module, "WakeWordListener", _WakeWordListener)
    monkeypatch.setattr(
        channel_module,
        "ActivationCoordinator",
        create_activation_coordinator,
    )
    external_activation = ExternalActivationSource()
    gateway_session = _GatewaySession()
    voice_channel = VoiceChannel(
        gateway_session=cast(GatewayVoiceSession, gateway_session),
        activation_sources=(external_activation,),
        audio_input=audio_input,
        audio_output=audio_output,
    )
    asyncio.run(voice_channel.stop())

    assert configured_sources[1:] == (external_activation,)


async def _settle() -> None:
    for _ in range(20):
        await asyncio.sleep(0)
