from gateway_rest_client import (
    AudioEncoding,
    VoiceSessionSnapshotResponse,
    VoiceTurnStatus,
)
from gateway_rest_client import AudioFormat as GatewayAudioFormat
from gateway_rpc_client.models import (
    Activation,
    VoiceAssistantAudioCompleted,
    VoiceAssistantAudioStarted,
    VoiceAssistantTextStarted,
    VoiceAssistantToolCompleted,
    VoiceAssistantToolStarted,
    VoiceConversationEnded,
    VoiceConversationInactivityCountdown,
    VoiceConversationStarted,
    VoiceEventMessage,
    VoiceSessionClosed,
    VoiceTranscriptFinal,
    VoiceTranscriptPartial,
    VoiceTurnCancelled,
    VoiceTurnCompleted,
    VoiceTurnDiscarded,
    VoiceTurnFailed,
    VoiceTurnStarted,
)
from voice.activation import ActivationKind
from voice.audio import AudioFormat
from voice.backend import (
    ActiveTurn,
    AssistantTextStarted,
    AssistantToolCompleted,
    AssistantToolStarted,
    BackendEvent,
    BackendSessionState,
    ConversationCountdown,
    ConversationEnded,
    ConversationStarted,
    SessionClosed,
    TranscriptCompleted,
    TranscriptUpdated,
    TurnCompleted,
    TurnDiscarded,
    TurnFailed,
    TurnPhase,
    TurnRef,
    TurnStarted,
)

_PHASES = {
    VoiceTurnStatus.LISTENING: TurnPhase.LISTENING,
    VoiceTurnStatus.TRANSCRIBING: TurnPhase.TRANSCRIBING,
    VoiceTurnStatus.WAITING_FOR_ASSISTANT: TurnPhase.WAITING_FOR_ASSISTANT,
    VoiceTurnStatus.SPEAKING: TurnPhase.SPEAKING,
}


def backend_event(event: VoiceEventMessage) -> BackendEvent | None:
    match event:
        case VoiceConversationStarted():
            return ConversationStarted()
        case VoiceConversationInactivityCountdown():
            return ConversationCountdown(remaining_seconds=event.remaining_seconds)
        case VoiceConversationEnded():
            return ConversationEnded(reason=event.reason)
        case VoiceTurnStarted():
            return TurnStarted(
                turn=TurnRef(event.voice_turn_id),
                proactive=event.activation is Activation.PROACTIVE,
            )
        case VoiceTranscriptPartial():
            return TranscriptUpdated(turn=TurnRef(event.voice_turn_id))
        case VoiceTranscriptFinal():
            return TranscriptCompleted(turn=TurnRef(event.voice_turn_id))
        case VoiceAssistantTextStarted():
            return AssistantTextStarted(turn=TurnRef(event.voice_turn_id))
        case VoiceAssistantToolStarted():
            return AssistantToolStarted(
                turn=TurnRef(event.voice_turn_id), name=event.name
            )
        case VoiceAssistantToolCompleted():
            return AssistantToolCompleted(
                turn=TurnRef(event.voice_turn_id), name=event.name
            )
        case VoiceAssistantAudioStarted() | VoiceAssistantAudioCompleted():
            # The media stream itself marks where a response's audio starts
            # and ends.
            return None
        case VoiceTurnCompleted() | VoiceTurnCancelled():
            return TurnCompleted(turn=TurnRef(event.voice_turn_id))
        case VoiceTurnDiscarded():
            return TurnDiscarded(turn=TurnRef(event.voice_turn_id))
        case VoiceTurnFailed():
            return TurnFailed(turn=TurnRef(event.voice_turn_id), message=event.message)
        case VoiceSessionClosed():
            return SessionClosed(reason=event.reason)


def session_state(snapshot: VoiceSessionSnapshotResponse) -> BackendSessionState:
    active = next(
        (turn for turn in snapshot.turns if turn.id == snapshot.active_turn_id),
        None,
    )
    if active is None or active.status not in _PHASES:
        return BackendSessionState()
    return BackendSessionState(
        active_turn=ActiveTurn(turn=TurnRef(active.id), phase=_PHASES[active.status])
    )


def gateway_activation(kind: ActivationKind) -> Activation:
    return Activation(kind.value)


def gateway_audio_format(audio_format: AudioFormat) -> GatewayAudioFormat:
    return GatewayAudioFormat(
        encoding=AudioEncoding.PCM_S16LE,
        sample_rate=audio_format.sample_rate,
        channels=audio_format.channels,
    )


def voice_audio_format(audio_format: GatewayAudioFormat) -> AudioFormat:
    return AudioFormat(
        sample_rate=audio_format.sample_rate,
        channels=audio_format.channels,
    )
