from pyrpckit import Inject, RpcChannel

from gateway.features.voice.application import VoiceTurnService
from gateway.features.voice.presentation.rpc.models import (
    InterruptVoiceTurnParams,
    StartVoiceTurnParams,
    VoiceTurnCommandResult,
    VoiceTurnParams,
)
from gateway.presentation.rpc import (
    MediaNotConnectedRpcError,
    ResourceNotFoundError,
    VoiceTurnAlreadyActiveRpcError,
)

voice_turn_channel = RpcChannel(
    "voice_turn", namespace="voice.turn", raises=(ResourceNotFoundError,)
)


@voice_turn_channel.server.method(
    "start",
    raises=(MediaNotConnectedRpcError, VoiceTurnAlreadyActiveRpcError),
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


@voice_turn_channel.server.method("interrupt")
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


@voice_turn_channel.server.method("playback_completed")
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
