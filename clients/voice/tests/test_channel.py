import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import pytest

import voice.channel as channel_module
from voice import (
    ActivationSource,
    ExternalActivationSource,
    FollowUpSettings,
    Observer,
    ObserverContext,
    VoiceChannel,
)
from voice.audio import AudioInput, AudioOutput
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

    async def conversation_events(self) -> AsyncIterator[object]:
        await asyncio.Event().wait()
        yield

    async def media_frames(self) -> AsyncIterator[object]:
        await asyncio.Event().wait()
        yield

    async def close(self) -> None:
        self.closed = True


class _LifecycleObserver(Observer):
    def __init__(self) -> None:
        self.events: list[str] = []

    async def prepare(self, context: ObserverContext) -> None:
        self.events.append("prepared")

    async def on_channel_starting(self) -> None:
        self.events.append("started")

    async def on_channel_stopped(self) -> None:
        self.events.append("stopped")


def test_runs_and_closes_an_injected_voice_stack(
    tmp_path: Path,
    monkeypatch,
    audio_input: AudioInput,
    audio_output: AudioOutput,
) -> None:
    recording_path = tmp_path / "conversation.wav"
    observer = _LifecycleObserver()
    gateway_session = _GatewaySession()
    monkeypatch.setattr(channel_module, "WakeWordListener", _WakeWordListener)
    voice_channel = VoiceChannel(
        gateway_session=cast(GatewayVoiceSession, gateway_session),
        audio_input=audio_input,
        audio_output=audio_output,
        observers=(observer,),
        recording_path=recording_path,
    )

    result = asyncio.run(voice_channel.start())
    asyncio.run(voice_channel.stop())

    assert result.recording_path == recording_path
    assert not recording_path.exists()
    assert gateway_session.closed
    assert observer.events == ["prepared", "started", "stopped"]

    with pytest.raises(RuntimeError, match="Voice channel is stopped"):
        asyncio.run(voice_channel.start())


def test_configures_follow_up_timeout(
    monkeypatch,
    audio_input: AudioInput,
    audio_output: AudioOutput,
) -> None:
    configured_settings: FollowUpSettings | None = None
    follow_up_handler = channel_module.FollowUpHandler

    def create_follow_up_handler(*, event_bus, settings):
        nonlocal configured_settings
        configured_settings = settings
        return follow_up_handler(event_bus=event_bus, settings=settings)

    monkeypatch.setattr(channel_module, "WakeWordListener", _WakeWordListener)
    monkeypatch.setattr(channel_module, "FollowUpHandler", create_follow_up_handler)
    gateway_session = _GatewaySession()
    voice_channel = VoiceChannel(
        gateway_session=cast(GatewayVoiceSession, gateway_session),
        audio_input=audio_input,
        audio_output=audio_output,
        follow_up_settings=FollowUpSettings(
            window_seconds=7.5,
            countdown_seconds=2,
        ),
    )
    asyncio.run(voice_channel.stop())

    assert configured_settings == FollowUpSettings(
        window_seconds=7.5,
        countdown_seconds=2,
    )


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
