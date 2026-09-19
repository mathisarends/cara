import logging
from uuid import UUID

from pyrpckit import (
    Inject,
    RpcBinaryInput,
    RpcBinaryOutput,
    RpcChannel,
    RpcConnection,
    RpcConnectionClose,
)

from gateway.features.voice.application import VoiceSessionService, VoiceTurnService
from gateway.features.voice.presentation.media.framing import MediaFrame, MediaFrameKind
from gateway.features.voice.presentation.media.sessions import InMemoryMediaSessions

logger = logging.getLogger(__name__)

media_channel = RpcChannel("voice_media", namespace="voice")


@media_channel.server.stream(
    "media",
    input_content_type="application/octet-stream",
)
async def voice_media_stream(
    voice_session_id: UUID,
    frames: Inject[RpcBinaryInput],
    output: Inject[RpcBinaryOutput],
    connection: Inject[RpcConnection],
    sessions: Inject[VoiceSessionService],
    turns: Inject[VoiceTurnService],
    media: Inject[InMemoryMediaSessions],
) -> None:
    await sessions.get(voice_session_id)
    if not await media.connect(voice_session_id, connection, output):
        await connection.close(
            RpcConnectionClose.POLICY_VIOLATION,
            reason="Voice session already has a media owner",
        )
        return
    try:
        async for payload in frames:
            frame = MediaFrame.decode(payload)
            if frame.kind not in {MediaFrameKind.INPUT_PCM, MediaFrameKind.INPUT_END}:
                raise ValueError("Clients may only send input media frames")
            await turns.receive_media(
                voice_session_id,
                frame.voice_turn_index,
                frame.sequence,
                frame.payload,
                end=frame.kind is MediaFrameKind.INPUT_END,
            )
    except ValueError as error:
        logger.warning("Invalid media frame for %s: %s", voice_session_id, error)
        await connection.close(RpcConnectionClose.PROTOCOL_ERROR, reason=str(error))
    finally:
        await media.release(voice_session_id, connection)
        await turns.media_disconnected(voice_session_id)
