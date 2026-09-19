from fastapi_canon import Error, ErrorRegistry

from gateway.features.voice.domain import (
    InvalidVoiceSessionError,
    VoiceRecordingNotFoundError,
    VoiceSessionAlreadyOpenError,
    VoiceSessionClosedError,
    VoiceSessionNotFoundError,
    VoiceTurnNotFoundError,
)

VOICE_SESSION_NOT_FOUND = Error(
    VoiceSessionNotFoundError,
    status=404,
    code="voice_session_not_found",
    title="Voice session not found",
    detail=str,
)
VOICE_TURN_NOT_FOUND = Error(
    VoiceTurnNotFoundError,
    status=404,
    code="voice_turn_not_found",
    title="Voice turn not found",
    detail=str,
)
VOICE_RECORDING_NOT_FOUND = Error(
    VoiceRecordingNotFoundError,
    status=404,
    code="voice_recording_not_found",
    title="Voice recording not found",
    detail=str,
)
VOICE_SESSION_ALREADY_OPEN = Error(
    VoiceSessionAlreadyOpenError,
    status=409,
    code="voice_session_already_open",
    title="Voice session already open",
    detail=str,
)
VOICE_SESSION_CLOSED = Error(
    VoiceSessionClosedError,
    status=409,
    code="voice_session_closed",
    title="Voice session closed",
    detail=str,
)
INVALID_VOICE_SESSION = Error(
    InvalidVoiceSessionError,
    status=422,
    code="invalid_voice_session",
    title="Invalid voice session",
    detail=str,
)

VOICE_ERRORS = ErrorRegistry(
    name="voice",
    errors=[
        VOICE_SESSION_NOT_FOUND,
        VOICE_TURN_NOT_FOUND,
        VOICE_RECORDING_NOT_FOUND,
        VOICE_SESSION_ALREADY_OPEN,
        VOICE_SESSION_CLOSED,
        INVALID_VOICE_SESSION,
    ],
)
