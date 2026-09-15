import asyncio
from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from voice.audio import AudioPlayback, EventAudioPlayer
from voice.events import (
    AssistantPlaybackCompleted,
    AssistantResponseStarted,
    AssistantSpeechStarted,
    AssistantTextChunk,
    AssistantToolCompleted,
    AssistantToolStarted,
    AssistantTurnStarted,
    FollowUpCountdown,
    FollowUpTimedOut,
    SessionEnded,
    SessionStarted,
    UserSpeechEnded,
    UserSpeechStarted,
    UserTurnStarted,
    VoiceTurnFailed,
    VoiceTurnInterrupted,
    VoiceTurnTimedOut,
    WakeWordDetected,
)
from voice.events.bus import EventBus
from voice.events.models import VoiceTurnEnded


@dataclass(frozen=True, slots=True)
class ObserverContext:
    """Dependencies made available to voice-channel observers."""

    audio_player: AudioPlayback


class Observer:
    """Callback interface for :class:`VoiceChannel` events.

    Subclass this class and pass instances to ``VoiceChannel(observers=...)``.
    Every callback is an async no-op by default, so subclasses only need to
    override the events they are interested in.
    """

    async def prepare(self, context: ObserverContext) -> None:
        """Prepare resources before the channel starts its wake-word cycle."""

    async def on_channel_starting(self) -> None: ...

    async def on_channel_stopped(self) -> None: ...

    async def on_wake_word_detected(
        self, name: str, score: float, sequence: int
    ) -> None: ...

    async def on_user_turn_started(self) -> None: ...

    async def on_assistant_turn_started(self) -> None: ...

    async def on_assistant_response_started(self, turn_id: UUID) -> None: ...

    async def on_assistant_text_chunk(self, turn_id: UUID, chunk: str) -> None: ...

    async def on_assistant_tool_started(self, name: str) -> None: ...

    async def on_assistant_tool_completed(self, name: str) -> None: ...

    async def on_user_inactivity_countdown(self, remaining_seconds: int) -> None: ...

    async def on_user_inactivity_timeout(self, timeout_seconds: float) -> None: ...

    async def on_agent_error(self, turn_id: UUID, message: str) -> None: ...

    async def on_voice_turn_timed_out(self, turn_id: UUID) -> None: ...

    async def on_user_started_speaking(self) -> None: ...

    async def on_user_stopped_speaking(self) -> None: ...

    async def on_assistant_started_responding(self) -> None: ...

    async def on_assistant_stopped_responding(self) -> None: ...

    async def on_assistant_interrupted(self, turn_id: UUID) -> None: ...

    async def on_voice_turn_ended(self, turn_id: UUID) -> None: ...


class ObserverBridge:
    def __init__(
        self,
        *,
        event_bus: EventBus,
        observers: Iterable[Observer],
    ) -> None:
        self._event_bus = event_bus
        self._observers = tuple(observers)
        self._context = ObserverContext(audio_player=EventAudioPlayer(event_bus))

    async def prepare(self) -> None:
        await asyncio.gather(
            *(observer.prepare(self._context) for observer in self._observers)
        )

    def setup(self) -> None:
        bus = self._event_bus
        for observer in self._observers:
            bus.on(
                SessionStarted,
                lambda _, observer=observer: observer.on_channel_starting(),
            )
            bus.on(
                SessionEnded,
                lambda _, observer=observer: observer.on_channel_stopped(),
            )
            bus.on(
                WakeWordDetected,
                lambda event, observer=observer: observer.on_wake_word_detected(
                    event.name, event.score, event.sequence
                ),
            )
            bus.on(
                UserTurnStarted,
                lambda _, observer=observer: observer.on_user_turn_started(),
            )
            bus.on(
                AssistantTurnStarted,
                lambda _, observer=observer: observer.on_assistant_turn_started(),
            )
            bus.on(
                AssistantResponseStarted,
                lambda event, observer=observer: observer.on_assistant_response_started(
                    event.turn_id
                ),
            )
            bus.on(
                AssistantTextChunk,
                lambda event, observer=observer: observer.on_assistant_text_chunk(
                    event.turn_id, event.chunk
                ),
            )
            bus.on(
                AssistantToolStarted,
                lambda event, observer=observer: observer.on_assistant_tool_started(
                    event.name
                ),
            )
            bus.on(
                AssistantToolCompleted,
                lambda event, observer=observer: observer.on_assistant_tool_completed(
                    event.name
                ),
            )
            bus.on(
                FollowUpCountdown,
                lambda event, observer=observer: observer.on_user_inactivity_countdown(
                    event.remaining_seconds
                ),
            )
            bus.on(
                FollowUpTimedOut,
                lambda event, observer=observer: observer.on_user_inactivity_timeout(
                    event.timeout_seconds
                ),
            )
            bus.on(
                VoiceTurnFailed,
                lambda event, observer=observer: observer.on_agent_error(
                    event.turn_id, event.message
                ),
            )
            bus.on(
                VoiceTurnTimedOut,
                lambda event, observer=observer: observer.on_voice_turn_timed_out(
                    event.turn_id
                ),
            )
            bus.on(
                UserSpeechStarted,
                lambda _, observer=observer: observer.on_user_started_speaking(),
            )
            bus.on(
                UserSpeechEnded,
                lambda _, observer=observer: observer.on_user_stopped_speaking(),
            )
            bus.on(
                AssistantSpeechStarted,
                lambda _, observer=observer: observer.on_assistant_started_responding(),
            )
            bus.on(
                AssistantPlaybackCompleted,
                lambda _, observer=observer: observer.on_assistant_stopped_responding(),
            )
            bus.on(
                VoiceTurnInterrupted,
                lambda event, observer=observer: observer.on_assistant_interrupted(
                    event.turn_id
                ),
            )
            bus.on(
                VoiceTurnEnded,
                lambda event, observer=observer: observer.on_voice_turn_ended(
                    event.turn_id
                ),
            )
