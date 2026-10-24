from fastapi_rpckit import Inject, RpcChannel

from gateway.features.voice.application import VoiceTurnService
from gateway.features.voice.presentation.rpc.errors import (
    INVALID_VOICE_TURN_TRANSITION,
    MEDIA_NOT_CONNECTED,
    VOICE_SESSION_CLOSED,
    VOICE_TURN_ALREADY_ACTIVE,
)
from gateway.features.voice.presentation.rpc.models import (
    InterruptVoiceTurnParams,
    StartVoiceTurnParams,
    VoiceTurnCommandResult,
    VoiceTurnParams,
)
from gateway.rpc.errors import RESOURCE_NOT_FOUND

voice_turn_channel = RpcChannel("voice_turn", namespace="voice.turn")


@voice_turn_channel.method(
    "start",
    raises=(
        RESOURCE_NOT_FOUND,
        MEDIA_NOT_CONNECTED,
        VOICE_TURN_ALREADY_ACTIVE,
        VOICE_SESSION_CLOSED,
    ),
)
async def start_voice_turn(
    params: StartVoiceTurnParams,
    voice_turn_service: Inject[VoiceTurnService],
) -> VoiceTurnCommandResult:
    turn = await voice_turn_service.start(params.voice_session_id, params.activation)
    return VoiceTurnCommandResult(
        voice_session_id=params.voice_session_id,
        voice_turn_id=turn.id,
    )


@voice_turn_channel.method("interrupt", raises=(RESOURCE_NOT_FOUND,))
async def interrupt_voice_turn(
    params: InterruptVoiceTurnParams,
    voice_turn_service: Inject[VoiceTurnService],
) -> VoiceTurnCommandResult:
    turn = await voice_turn_service.interrupt(params.voice_turn_id)
    voice_session_id = await voice_turn_service.voice_session_id_for(turn.id)
    return VoiceTurnCommandResult(
        voice_session_id=voice_session_id,
        voice_turn_id=turn.id,
    )


@voice_turn_channel.method(
    "playback_completed",
    raises=(
        RESOURCE_NOT_FOUND,
        INVALID_VOICE_TURN_TRANSITION,
    ),
)
async def complete_voice_playback(
    params: VoiceTurnParams,
    voice_turn_service: Inject[VoiceTurnService],
) -> VoiceTurnCommandResult:
    turn = await voice_turn_service.playback_completed(params.voice_turn_id)
    voice_session_id = await voice_turn_service.voice_session_id_for(turn.id)
    return VoiceTurnCommandResult(
        voice_session_id=voice_session_id,
        voice_turn_id=turn.id,
    )
