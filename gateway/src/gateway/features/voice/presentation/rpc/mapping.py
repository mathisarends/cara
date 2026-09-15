from gateway.features.voice.application import VoiceEvent
from gateway.features.voice.presentation.rpc.models import (
    VOICE_EVENT_ADAPTER,
    VoiceEventMessage,
)


def voice_event(event: VoiceEvent) -> VoiceEventMessage:
    message = {
        "type": event.type,
        "event_id": event.event_id,
        "timestamp": event.timestamp,
        "voice_session_id": event.voice_session_id,
        "session_id": event.session_id,
        **event.data,
    }
    if event.voice_turn_id is not None:
        message["voice_turn_id"] = event.voice_turn_id
    if event.sequence is not None:
        message["sequence"] = event.sequence
    if event.revision is not None:
        message["revision"] = event.revision
    return VOICE_EVENT_ADAPTER.validate_python(message)
