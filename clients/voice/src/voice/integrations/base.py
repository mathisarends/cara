from dataclasses import dataclass
from uuid import UUID

from voice.audio import AudioPlayback


@dataclass(frozen=True, slots=True)
class VoiceIntegrationContext:
    """Dependencies made available to local voice integrations."""

    audio_player: AudioPlayback


class VoiceIntegration:
    """Local feature that reacts to semantic :class:`VoiceChannel` events.

    Subclass this class and pass instances to ``VoiceChannel(integrations=...)``.
    Every callback is an async no-op by default, so subclasses only need to
    override the events they are interested in.
    """

    async def prepare(self, context: VoiceIntegrationContext) -> None:
        """Prepare resources before the channel starts its wake-word cycle."""

    async def on_channel_starting(self) -> None: ...

    async def on_channel_stopped(self) -> None: ...

    async def on_wake_word_detected(
        self, name: str, score: float, sequence: int
    ) -> None: ...

    async def on_user_turn_started(self) -> None: ...

    async def on_assistant_turn_started(self) -> None: ...

    async def on_assistant_response_started(self, turn_id: UUID) -> None: ...

    async def on_assistant_text_started(self, turn_id: UUID) -> None: ...

    async def on_assistant_tool_started(self, name: str) -> None: ...

    async def on_assistant_tool_completed(self, name: str) -> None: ...

    async def on_voice_conversation_started(self) -> None: ...

    async def on_voice_conversation_inactivity_countdown(
        self, remaining_seconds: int
    ) -> None: ...

    async def on_voice_conversation_ended(self, reason: str) -> None: ...

    async def on_agent_error(self, turn_id: UUID, message: str) -> None: ...

    async def on_voice_turn_timed_out(self, turn_id: UUID) -> None: ...

    async def on_user_started_speaking(self) -> None: ...

    async def on_user_stopped_speaking(self) -> None: ...

    async def on_assistant_started_responding(self) -> None: ...

    async def on_assistant_stopped_responding(self) -> None: ...

    async def on_assistant_interrupted(self, turn_id: UUID) -> None: ...

    async def on_voice_turn_ended(self, turn_id: UUID) -> None: ...
