import asyncio
import logging
from pathlib import Path
from typing import cast
from uuid import uuid4

from voice.conversation import ConversationAudioMixer, ConversationAudioRecorder
from voice.events import (
    AssistantAudioChunk,
    AssistantPlaybackCompleted,
    AssistantSpeechStarted,
    UserAudioChunk,
)
from voice.events.bus import EventBus
from voice.events.models import VoiceResourcesClosing


class _Mixer:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.user_chunks: list[bytes] = []
        self.assistant_chunks: list[bytes] = []
        self.finalized = 0
        self.saved = 0

    def feed_user(self, chunk: bytes) -> None:
        self.user_chunks.append(chunk)

    def feed_assistant(self, chunk: bytes) -> None:
        self.assistant_chunks.append(chunk)

    def finalize(self) -> None:
        self.finalized += 1

    def save(self) -> None:
        self.saved += 1


def test_records_session_audio_and_suppresses_user_echo(
    tmp_path: Path, event_bus: EventBus, caplog
) -> None:
    mixer = _Mixer(tmp_path / "recording.wav")
    ConversationAudioRecorder(event_bus, cast(ConversationAudioMixer, mixer))
    caplog.set_level(logging.INFO)

    async def run() -> None:
        turn_id = uuid4()
        await event_bus.dispatch(UserAudioChunk(sequence=1, chunk=b"user"))
        await event_bus.dispatch(AssistantSpeechStarted())
        await event_bus.dispatch(UserAudioChunk(sequence=2, chunk=b"echo"))
        await event_bus.dispatch(
            AssistantAudioChunk(turn_id=turn_id, chunk=b"assistant")
        )
        await event_bus.dispatch(AssistantPlaybackCompleted(turn_id=turn_id))
        await event_bus.dispatch(VoiceResourcesClosing())

    asyncio.run(run())

    assert mixer.user_chunks == [b"user"]
    assert mixer.assistant_chunks == [b"assistant"]
    assert mixer.finalized == 1
    assert mixer.saved == 1
    assert "Recording saved" in caplog.text
