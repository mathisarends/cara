from pyrpckit import Inject, RpcInternalError, RpcInvalidParamsError, RpcModule

from gateway.features.voice.application import VoiceTurnService
from gateway.features.voice.presentation.rpc.models import (
    InterruptVoiceTurnParams,
    StartVoiceTurnParams,
    VoiceRpcMethod,
    VoiceTurnCommandResult,
    VoiceTurnParams,
)
from gateway.presentation.rpc import (
    MediaNotConnectedRpcError,
    ResourceNotFoundError,
    VoiceTurnAlreadyActiveRpcError,
)

voice_module = RpcModule()


@voice_module.method(
    VoiceRpcMethod.TURN_START,
    errors=(
        RpcInvalidParamsError,
        ResourceNotFoundError,
        MediaNotConnectedRpcError,
        VoiceTurnAlreadyActiveRpcError,
        RpcInternalError,
    ),
)
async def start_voice_turn(
    params: StartVoiceTurnParams,
    turns: Inject[VoiceTurnService],
) -> VoiceTurnCommandResult:
    turn = await turns.start(params.voice_session_id, params.activation)
    return VoiceTurnCommandResult(
        voice_session_id=params.voice_session_id,
        voice_turn_id=turn.id,
    )


@voice_module.method(
    VoiceRpcMethod.TURN_INTERRUPT,
    errors=(ResourceNotFoundError, RpcInvalidParamsError, RpcInternalError),
)
async def interrupt_voice_turn(
    params: InterruptVoiceTurnParams,
    turns: Inject[VoiceTurnService],
) -> VoiceTurnCommandResult:
    turn = await turns.interrupt(params.voice_turn_id)
    voice_session_id = await turns.voice_session_id_for(turn.id)
    return VoiceTurnCommandResult(
        voice_session_id=voice_session_id,
        voice_turn_id=turn.id,
    )


@voice_module.method(
    VoiceRpcMethod.TURN_PLAYBACK_COMPLETED,
    errors=(ResourceNotFoundError, RpcInvalidParamsError, RpcInternalError),
)
async def complete_voice_playback(
    params: VoiceTurnParams,
    turns: Inject[VoiceTurnService],
) -> VoiceTurnCommandResult:
    turn = await turns.playback_completed(params.voice_turn_id)
    voice_session_id = await turns.voice_session_id_for(turn.id)
    return VoiceTurnCommandResult(
        voice_session_id=voice_session_id,
        voice_turn_id=turn.id,
    )
