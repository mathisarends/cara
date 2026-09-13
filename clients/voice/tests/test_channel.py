import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol, cast

import pytest

import voice.channel as channel_module
from voice import (
    Activation,
    ActivationSource,
    ExternalActivationSource,
    FollowUpSettings,
    ListenActivation,
    Observer,
    ObserverContext,
    VoiceChannel,
)
from voice.audio import AudioInput, AudioOutput
from voice.llm import AgentSession, EchoAgentSession
from voice.stt import SpeechToText
from voice.tts import TextToSpeech
from voice.wakeword import WakeWordDetection


class _Closable(Protocol):
    closed: bool


class _Stoppable(Protocol):
    stopped: bool


class _WakeWordListener:
    phrase = "hey mycroft"

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def detections(self) -> AsyncIterator[WakeWordDetection]:
        if False:
            yield WakeWordDetection(sequence=0, score=0, name="")


class _ActivatingAgentSession(EchoAgentSession, ActivationSource):
    async def activations(self) -> AsyncIterator[Activation]:
        if False:
            yield ListenActivation()


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
    agent_session: AgentSession,
    audio_input: AudioInput,
    audio_output: AudioOutput,
    speech_to_text: SpeechToText,
    text_to_speech: TextToSpeech,
) -> None:
    recording_path = tmp_path / "conversation.wav"
    observer = _LifecycleObserver()
    monkeypatch.setattr(channel_module, "WakeWordListener", _WakeWordListener)
    voice_channel = VoiceChannel(
        agent_session=agent_session,
        audio_input=audio_input,
        audio_output=audio_output,
        speech_to_text=speech_to_text,
        text_to_speech=text_to_speech,
        observers=(observer,),
        recording_path=recording_path,
    )

    result = asyncio.run(voice_channel.start())
    asyncio.run(voice_channel.stop())

    assert result.recording_path == recording_path
    assert not recording_path.exists()
    assert _stoppable(audio_input).stopped
    assert _stoppable(audio_output).stopped
    assert _closable(speech_to_text).closed
    assert _closable(text_to_speech).closed
    assert observer.events == ["prepared", "started", "stopped"]

    with pytest.raises(RuntimeError, match="Voice channel is stopped"):
        asyncio.run(voice_channel.start())


def test_configures_follow_up_timeout(
    monkeypatch,
    agent_session: AgentSession,
    audio_input: AudioInput,
    audio_output: AudioOutput,
    speech_to_text: SpeechToText,
    text_to_speech: TextToSpeech,
) -> None:
    configured_settings: FollowUpSettings | None = None
    follow_up_handler = channel_module.FollowUpHandler

    def create_follow_up_handler(*, event_bus, settings):
        nonlocal configured_settings
        configured_settings = settings
        return follow_up_handler(
            event_bus=event_bus,
            settings=settings,
        )

    monkeypatch.setattr(channel_module, "WakeWordListener", _WakeWordListener)
    monkeypatch.setattr(
        channel_module,
        "FollowUpHandler",
        create_follow_up_handler,
    )

    voice_channel = VoiceChannel(
        agent_session=agent_session,
        audio_input=audio_input,
        audio_output=audio_output,
        speech_to_text=speech_to_text,
        text_to_speech=text_to_speech,
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
    speech_to_text: SpeechToText,
    text_to_speech: TextToSpeech,
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
    agent_session = _ActivatingAgentSession()
    external_activation = ExternalActivationSource()

    voice_channel = VoiceChannel(
        agent_session=agent_session,
        activation_sources=(external_activation,),
        audio_input=audio_input,
        audio_output=audio_output,
        speech_to_text=speech_to_text,
        text_to_speech=text_to_speech,
    )
    asyncio.run(voice_channel.stop())

    assert agent_session not in configured_sources
    assert configured_sources[1:] == (external_activation,)


def _closable(value: object) -> _Closable:
    return cast(_Closable, value)


def _stoppable(value: object) -> _Stoppable:
    return cast(_Stoppable, value)
