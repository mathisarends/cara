import logging
from pathlib import Path

from voice.events import (
    AssistantAudioChunk,
    AssistantPlaybackCompleted,
    AssistantSpeechStarted,
    UserAudioChunk,
)
from voice.events.bus import EventBus
from voice.events.models import VoiceResourcesClosing

from .audio_mixer import ConversationAudioMixer

logger = logging.getLogger(__name__)


class ConversationAudioRecorder:
    """Records user and assistant PCM published by a voice session."""

    def __init__(self, event_bus: EventBus, mixer: ConversationAudioMixer) -> None:
        self._mixer = mixer
        self._assistant_speaking = False

        event_bus.on(AssistantSpeechStarted, self._on_assistant_started)
        event_bus.on(AssistantPlaybackCompleted, self._on_assistant_stopped)
        event_bus.on(UserAudioChunk, self._on_user_audio)
        event_bus.on(AssistantAudioChunk, self._on_assistant_audio)
        event_bus.on(VoiceResourcesClosing, self._on_resources_closing)

    async def _on_assistant_started(self, _: AssistantSpeechStarted) -> None:
        self._assistant_speaking = True

    async def _on_assistant_stopped(self, _: AssistantPlaybackCompleted) -> None:
        self._assistant_speaking = False
        self._mixer.finalize()

    async def _on_user_audio(self, event: UserAudioChunk) -> None:
        if not self._assistant_speaking:
            self._mixer.feed_user(event.chunk)

    async def _on_assistant_audio(self, event: AssistantAudioChunk) -> None:
        self._mixer.feed_assistant(event.chunk)

    async def _on_resources_closing(self, _: VoiceResourcesClosing) -> None:
        self._mixer.save()
        logger.info("Recording saved to %s", self._mixer.path)


def create_recorder(
    event_bus: EventBus,
    recording_path: Path | None,
    *,
    user_sample_rate: int,
    assistant_sample_rate: int,
) -> ConversationAudioRecorder | None:
    """Start recording to ``recording_path``, or do nothing if it is None."""
    if recording_path is None:
        return None
    return ConversationAudioRecorder(
        event_bus,
        ConversationAudioMixer(
            recording_path,
            user_sample_rate=user_sample_rate,
            assistant_sample_rate=assistant_sample_rate,
        ),
    )
