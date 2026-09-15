from gateway.features.voice.domain import AudioFormat, VoiceSession, VoiceTurn
from gateway.features.voice.presentation.schemas import (
    AudioFormat as AudioFormatSchema,
)
from gateway.features.voice.presentation.schemas import (
    VoiceSessionListResponse,
    VoiceSessionResponse,
    VoiceSessionSnapshotResponse,
    VoiceTurnResponse,
)


def to_audio_format(value: AudioFormatSchema) -> AudioFormat:
    return AudioFormat(value.encoding, value.sample_rate, value.channels)


def to_voice_session_response(
    voice_session: VoiceSession,
    *,
    media_connected: bool,
) -> VoiceSessionResponse:
    return VoiceSessionResponse(
        id=voice_session.id,
        session_id=voice_session.session_id,
        device_id=voice_session.device_id,
        status=voice_session.status,
        input_format=_audio_format(voice_session.input_format),
        output_format=_audio_format(voice_session.output_format),
        media_path=f"/v1/voice-sessions/{voice_session.id}/media",
        media_connected=media_connected,
        created_at=voice_session.created_at,
        closed_at=voice_session.closed_at,
        close_reason=voice_session.close_reason,
    )


def to_voice_session_list_response(
    voice_sessions: tuple[VoiceSession, ...],
    connected: set,
) -> VoiceSessionListResponse:
    return VoiceSessionListResponse(
        voice_sessions=tuple(
            to_voice_session_response(item, media_connected=item.id in connected)
            for item in voice_sessions
        )
    )


def to_voice_session_snapshot_response(
    voice_session: VoiceSession,
    *,
    media_connected: bool,
) -> VoiceSessionSnapshotResponse:
    active = voice_session.active_turn
    return VoiceSessionSnapshotResponse(
        voice_session=to_voice_session_response(
            voice_session,
            media_connected=media_connected,
        ),
        turns=tuple(to_voice_turn_response(turn) for turn in voice_session.turns),
        active_turn_id=None if active is None else active.id,
        last_sequence=voice_session.last_sequence,
    )


def to_voice_turn_response(turn: VoiceTurn) -> VoiceTurnResponse:
    error = turn.error_message
    if turn.error_code and error:
        error = f"{turn.error_code}: {error}"
    elif turn.error_code:
        error = turn.error_code
    return VoiceTurnResponse(
        id=turn.id,
        index=turn.index,
        activation=turn.activation,
        status=turn.status,
        transcript=turn.transcript,
        user_message_id=turn.user_message_id,
        error=error,
        started_at=turn.created_at,
        input_ended_at=turn.input_ended_at,
        transcribed_at=turn.transcribed_at,
        speech_started_at=turn.speech_started_at,
        ended_at=turn.ended_at,
    )


def _audio_format(value: AudioFormat) -> AudioFormatSchema:
    return AudioFormatSchema(
        encoding=value.encoding,
        sample_rate=value.sample_rate,
        channels=value.channels,
    )
