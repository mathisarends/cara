import asyncio
import logging
from collections.abc import Coroutine, Iterable

from voice.integrations.base import VoiceIntegration, VoiceIntegrationContext
from voice.lifecycle import (
    AssistantSpeechCompleted,
    AssistantSpeechStarted,
    AssistantTextStarted,
    AssistantToolCompleted,
    AssistantToolStarted,
    AssistantTurnStarted,
    SessionStarted,
    SessionStopped,
    UserSpeechEnded,
    UserSpeechStarted,
    UserTurnStarted,
    VoiceConversationEnded,
    VoiceConversationInactivityCountdown,
    VoiceConversationStarted,
    VoiceLifecycleEvent,
    VoiceLifecycleObserver,
    VoiceTurnEnded,
    VoiceTurnFailed,
    VoiceTurnInterrupted,
    VoiceTurnTimedOut,
    WakeWordDetected,
)

logger = logging.getLogger(__name__)


class VoiceIntegrationNotifier(VoiceLifecycleObserver):
    """Starts integrations, forwards lifecycle events to them and stops them."""

    def __init__(self, integrations: Iterable[VoiceIntegration]) -> None:
        self._integrations = tuple(integrations)
        self._started: tuple[VoiceIntegration, ...] = ()

    async def start(self, context: VoiceIntegrationContext) -> None:
        results = await asyncio.gather(
            *(integration.prepare(context) for integration in self._integrations),
            return_exceptions=True,
        )
        # An integration may hold resources as soon as it prepared, so it
        # counts as started and is stopped even if another one failed.
        self._started = tuple(
            integration
            for integration, result in zip(self._integrations, results, strict=True)
            if not isinstance(result, BaseException)
        )
        failures = [result for result in results if isinstance(result, BaseException)]
        if len(failures) == 1:
            raise failures[0]
        if failures:
            raise BaseExceptionGroup("Voice integrations failed to prepare", failures)
        for integration in self._started:
            await integration.on_session_starting()

    async def on_lifecycle_event(self, event: VoiceLifecycleEvent) -> None:
        for integration in self._started:
            callback = _callback_for(integration, event)
            if callback is None:
                continue
            try:
                await callback
            except Exception:
                logger.exception(
                    "%s failed to handle %s",
                    type(integration).__name__,
                    type(event).__name__,
                )

    async def stop(self) -> None:
        started, self._started = self._started, ()
        for integration in started:
            try:
                await integration.on_session_stopped()
            except Exception:
                logger.exception("%s failed to stop", type(integration).__name__)


def _callback_for(
    integration: VoiceIntegration, event: VoiceLifecycleEvent
) -> Coroutine[None, None, None] | None:
    match event:
        case SessionStarted() | SessionStopped():
            # Integrations learn about these through start() and stop().
            return None
        case WakeWordDetected(name=name, score=score, sequence=sequence):
            return integration.on_wake_word_detected(name, score, sequence)
        case UserTurnStarted():
            return integration.on_user_turn_started()
        case UserSpeechStarted():
            return integration.on_user_started_speaking()
        case UserSpeechEnded():
            return integration.on_user_stopped_speaking()
        case AssistantTurnStarted(turn_id=turn_id):
            return integration.on_assistant_turn_started(turn_id)
        case AssistantTextStarted(turn_id=turn_id):
            return integration.on_assistant_text_started(turn_id)
        case AssistantToolStarted(name=name):
            return integration.on_assistant_tool_started(name)
        case AssistantToolCompleted(name=name):
            return integration.on_assistant_tool_completed(name)
        case AssistantSpeechStarted():
            return integration.on_assistant_started_responding()
        case AssistantSpeechCompleted():
            return integration.on_assistant_stopped_responding()
        case VoiceTurnInterrupted(turn_id=turn_id):
            return integration.on_assistant_interrupted(turn_id)
        case VoiceTurnTimedOut(turn_id=turn_id):
            return integration.on_voice_turn_timed_out(turn_id)
        case VoiceTurnFailed(turn_id=turn_id, message=message):
            return integration.on_agent_error(turn_id, message)
        case VoiceTurnEnded(turn_id=turn_id):
            return integration.on_voice_turn_ended(turn_id)
        case VoiceConversationStarted():
            return integration.on_voice_conversation_started()
        case VoiceConversationInactivityCountdown(remaining_seconds=remaining):
            return integration.on_voice_conversation_inactivity_countdown(remaining)
        case VoiceConversationEnded(reason=reason):
            return integration.on_voice_conversation_ended(reason)
