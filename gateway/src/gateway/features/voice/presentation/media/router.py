import logging
from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import (
    APIRouter,
    WebSocket,
    WebSocketDisconnect,
    WebSocketException,
    status,
)

from gateway.features.voice.application import VoiceSessionService, VoiceTurnService
from gateway.features.voice.presentation.media.framing import MediaFrame, MediaFrameKind
from gateway.features.voice.presentation.media.sessions import InMemoryMediaSessions
from gateway.presentation.authentication import GatewayAuthenticator

logger = logging.getLogger(__name__)

media_router = APIRouter(tags=["voice"])


@media_router.websocket("/v1/voice-sessions/{voice_session_id}/media")
@inject
async def voice_media_socket(
    voice_session_id: UUID,
    socket: WebSocket,
    authenticator: FromDishka[GatewayAuthenticator],
    sessions: FromDishka[VoiceSessionService],
    turns: FromDishka[VoiceTurnService],
    media: FromDishka[InMemoryMediaSessions],
) -> None:
    authenticator.authenticate(socket)
    await sessions.get(voice_session_id)
    if not await media.connect(voice_session_id, socket):
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Voice session already has a media owner",
        )
    await socket.accept()
    try:
        while True:
            frame = MediaFrame.decode(await socket.receive_bytes())
            if frame.kind not in {MediaFrameKind.INPUT_PCM, MediaFrameKind.INPUT_END}:
                raise ValueError("Clients may only send input media frames")
            await turns.receive_media(
                voice_session_id,
                frame.voice_turn_index,
                frame.sequence,
                frame.payload,
                end=frame.kind is MediaFrameKind.INPUT_END,
            )
    except WebSocketDisconnect:
        pass
    except ValueError as error:
        logger.warning("Invalid media frame for %s: %s", voice_session_id, error)
        await socket.close(code=status.WS_1003_UNSUPPORTED_DATA, reason=str(error))
    finally:
        await media.release(voice_session_id, socket)
        await turns.media_disconnected(voice_session_id)
