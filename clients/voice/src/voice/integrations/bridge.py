import asyncio
from collections.abc import Iterable

from voice.audio import EventAudioPlayer
from voice.events import (
    AssistantPlaybackCompleted,
    AssistantResponseStarted,
    AssistantSpeechStarted,
    AssistantTextStarted,
    AssistantToolCompleted,
    AssistantToolStarted,
    AssistantTurnStarted,
    SessionEnded,
    SessionStarted,
    UserSpeechEnded,
    UserSpeechStarted,
    UserTurnStarted,
    VoiceConversationEnded,
    VoiceConversationInactivityCountdown,
    VoiceConversationStarted,
    VoiceTurnFailed,
    VoiceTurnInterrupted,
    VoiceTurnTimedOut,
    WakeWordDetected,
)
from voice.events.bus import EventBus
from voice.events.models import VoiceTurnEnded
from voice.integrations.base import VoiceIntegration, VoiceIntegrationContext


class VoiceIntegrationBridge:
    def __init__(
        self,
        *,
        event_bus: EventBus,
        integrations: Iterable[VoiceIntegration],
    ) -> None:
        self._event_bus = event_bus
        self._integrations = tuple(integrations)
        self._context = VoiceIntegrationContext(
            audio_player=EventAudioPlayer(event_bus)
        )

    async def prepare(self) -> None:
        await asyncio.gather(
            *(integration.prepare(self._context) for integration in self._integrations)
        )

    def setup(self) -> None:
        bus = self._event_bus
        for integration in self._integrations:
            bus.on(
                SessionStarted,
                lambda _, integration=integration: integration.on_channel_starting(),
            )
            bus.on(
                SessionEnded,
                lambda _, integration=integration: integration.on_channel_stopped(),
            )
            bus.on(
                WakeWordDetected,
                lambda event, integration=integration: (
                    integration.on_wake_word_detected(
                        event.name, event.score, event.sequence
                    )
                ),
            )
            bus.on(
                UserTurnStarted,
                lambda _, integration=integration: integration.on_user_turn_started(),
            )
            bus.on(
                AssistantTurnStarted,
                lambda _, integration=integration: (
                    integration.on_assistant_turn_started()
                ),
            )
            bus.on(
                AssistantResponseStarted,
                lambda event, integration=integration: (
                    integration.on_assistant_response_started(event.turn_id)
                ),
            )
            bus.on(
                AssistantTextStarted,
                lambda event, integration=integration: (
                    integration.on_assistant_text_started(event.turn_id)
                ),
            )
            bus.on(
                AssistantToolStarted,
                lambda event, integration=integration: (
                    integration.on_assistant_tool_started(event.name)
                ),
            )
            bus.on(
                AssistantToolCompleted,
                lambda event, integration=integration: (
                    integration.on_assistant_tool_completed(event.name)
                ),
            )
            bus.on(
                VoiceConversationStarted,
                lambda _, integration=integration: (
                    integration.on_voice_conversation_started()
                ),
            )
            bus.on(
                VoiceConversationInactivityCountdown,
                lambda event, integration=integration: (
                    integration.on_voice_conversation_inactivity_countdown(
                        event.remaining_seconds
                    )
                ),
            )
            bus.on(
                VoiceConversationEnded,
                lambda event, integration=integration: (
                    integration.on_voice_conversation_ended(event.reason)
                ),
            )
            bus.on(
                VoiceTurnFailed,
                lambda event, integration=integration: integration.on_agent_error(
                    event.turn_id, event.message
                ),
            )
            bus.on(
                VoiceTurnTimedOut,
                lambda event, integration=integration: (
                    integration.on_voice_turn_timed_out(event.turn_id)
                ),
            )
            bus.on(
                UserSpeechStarted,
                lambda _, integration=integration: (
                    integration.on_user_started_speaking()
                ),
            )
            bus.on(
                UserSpeechEnded,
                lambda _, integration=integration: (
                    integration.on_user_stopped_speaking()
                ),
            )
            bus.on(
                AssistantSpeechStarted,
                lambda _, integration=integration: (
                    integration.on_assistant_started_responding()
                ),
            )
            bus.on(
                AssistantPlaybackCompleted,
                lambda _, integration=integration: (
                    integration.on_assistant_stopped_responding()
                ),
            )
            bus.on(
                VoiceTurnInterrupted,
                lambda event, integration=integration: (
                    integration.on_assistant_interrupted(event.turn_id)
                ),
            )
            bus.on(
                VoiceTurnEnded,
                lambda event, integration=integration: integration.on_voice_turn_ended(
                    event.turn_id
                ),
            )
