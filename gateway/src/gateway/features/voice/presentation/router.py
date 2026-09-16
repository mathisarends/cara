from typing import Annotated
from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import Depends, Query, status
from fastapi_canon import CanonRouter

from gateway.features.voice.application import VoiceSessionService
from gateway.features.voice.domain import VoiceSessionStatus
from gateway.features.voice.presentation.errors import (
    INVALID_VOICE_SESSION,
    VOICE_ERRORS,
    VOICE_SESSION_ALREADY_OPEN,
    VOICE_SESSION_NOT_FOUND,
    VOICE_TURN_NOT_FOUND,
)
from gateway.features.voice.presentation.mapper import (
    to_audio_format,
    to_voice_session_list_response,
    to_voice_session_response,
    to_voice_session_snapshot_response,
    to_voice_turn_response,
)
from gateway.features.voice.presentation.schemas import (
    OpenVoiceSessionRequest,
    VoiceSessionListResponse,
    VoiceSessionResponse,
    VoiceSessionSnapshotResponse,
    VoiceTurnResponse,
)
from gateway.presentation.authentication import require_token

voice_router = CanonRouter(
    prefix="/v1/voice-sessions",
    tags=["voice"],
    route_class=DishkaRoute,
    error_registry=VOICE_ERRORS,
    dependencies=[Depends(require_token)],
)


@voice_router.post(
    "",
    operation_id="open_voice_session",
    response_model=VoiceSessionResponse,
    status_code=status.HTTP_201_CREATED,
    raises=[VOICE_SESSION_ALREADY_OPEN, INVALID_VOICE_SESSION],
)
async def open_voice_session(
    request: OpenVoiceSessionRequest,
    service: FromDishka[VoiceSessionService],
) -> VoiceSessionResponse:
    voice_session = await service.open(
        request.session_id,
        request.room,
        tuple(to_audio_format(item) for item in request.input_formats),
        tuple(to_audio_format(item) for item in request.output_formats),
    )
    return to_voice_session_response(voice_session, media_connected=False)


@voice_router.get(
    "",
    operation_id="list_voice_sessions",
    response_model=VoiceSessionListResponse,
)
async def list_voice_sessions(
    service: FromDishka[VoiceSessionService],
    session_id: UUID | None = None,
    room: Annotated[str | None, Query(min_length=1, pattern=r"\S")] = None,
    status_filter: Annotated[VoiceSessionStatus | None, Query(alias="status")] = None,
) -> VoiceSessionListResponse:
    voice_sessions = await service.list(
        session_id=session_id,
        room=room,
        status=status_filter,
    )
    connected = {item.id for item in voice_sessions if service.media_connected(item.id)}
    return to_voice_session_list_response(voice_sessions, connected)


@voice_router.get(
    "/{voice_session_id}",
    operation_id="get_voice_session",
    response_model=VoiceSessionSnapshotResponse,
    raises=[VOICE_SESSION_NOT_FOUND],
)
async def get_voice_session(
    voice_session_id: UUID,
    service: FromDishka[VoiceSessionService],
) -> VoiceSessionSnapshotResponse:
    voice_session = await service.get(voice_session_id)
    return to_voice_session_snapshot_response(
        voice_session,
        media_connected=service.media_connected(voice_session_id),
    )


@voice_router.post(
    "/{voice_session_id}/close",
    operation_id="close_voice_session",
    response_model=VoiceSessionResponse,
    raises=[VOICE_SESSION_NOT_FOUND],
)
async def close_voice_session(
    voice_session_id: UUID,
    service: FromDishka[VoiceSessionService],
) -> VoiceSessionResponse:
    voice_session = await service.close(voice_session_id)
    return to_voice_session_response(voice_session, media_connected=False)


@voice_router.get(
    "/{voice_session_id}/turns/{voice_turn_id}",
    operation_id="get_voice_turn",
    response_model=VoiceTurnResponse,
    raises=[VOICE_SESSION_NOT_FOUND, VOICE_TURN_NOT_FOUND],
)
async def get_voice_turn(
    voice_session_id: UUID,
    voice_turn_id: UUID,
    service: FromDishka[VoiceSessionService],
) -> VoiceTurnResponse:
    voice_session = await service.get(voice_session_id)
    return to_voice_turn_response(voice_session.get_turn(voice_turn_id))
