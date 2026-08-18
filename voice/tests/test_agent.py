import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol, cast

import pytest

import voice.agent as agent_module
from voice import VoiceAgent
from voice.audio import AudioInput, AudioOutput
from voice.llm import AgentSession
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
    monkeypatch.setattr(agent_module, "WakeWordListener", _WakeWordListener)
    agent = VoiceAgent(
        agent_session=agent_session,
        audio_input=audio_input,
        audio_output=audio_output,
        speech_to_text=speech_to_text,
        text_to_speech=text_to_speech,
        recording_path=recording_path,
    )

    result = asyncio.run(agent.start())
    asyncio.run(agent.stop())

    assert result.recording_path == recording_path
    assert result.conversation_history == ()
    assert not recording_path.exists()
    assert _stoppable(audio_input).stopped
    assert _stoppable(audio_output).stopped
    assert _closable(speech_to_text).closed
    assert _closable(text_to_speech).closed

    with pytest.raises(RuntimeError, match="Voice agent is stopped"):
        asyncio.run(agent.start())


def _closable(value: object) -> _Closable:
    return cast(_Closable, value)


def _stoppable(value: object) -> _Stoppable:
    return cast(_Stoppable, value)
