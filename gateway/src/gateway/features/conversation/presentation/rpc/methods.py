from fastapi_rpckit import Inject, RpcChannel

from gateway.features.conversation.application import TurnService
from gateway.features.conversation.presentation.rpc.errors import (
    NO_ACTIVE_TURN,
    TURN_ALREADY_RUNNING,
)
from gateway.features.conversation.presentation.rpc.models import (
    SessionParams,
    StartTurnParams,
    SteerTurnParams,
    TurnCommandResult,
)
from gateway.rpc.errors import RESOURCE_NOT_FOUND

turn_channel = RpcChannel("turn", raises=(RESOURCE_NOT_FOUND,))


@turn_channel.method("prepare")
async def prepare_turn(
    params: SessionParams,
    turn_service: Inject[TurnService],
) -> TurnCommandResult:
    await turn_service.prepare(params.session_id)
    return TurnCommandResult(session_id=params.session_id)


@turn_channel.method("start", raises=(TURN_ALREADY_RUNNING,))
async def start_turn(
    params: StartTurnParams,
    turn_service: Inject[TurnService],
) -> TurnCommandResult:
    await turn_service.start(
        session_id=params.session_id,
        text=params.message,
    )
    return TurnCommandResult(session_id=params.session_id)


@turn_channel.method("steer", raises=(NO_ACTIVE_TURN,))
async def steer_turn(
    params: SteerTurnParams,
    turn_service: Inject[TurnService],
) -> TurnCommandResult:
    await turn_service.steer(session_id=params.session_id, text=params.message)
    return TurnCommandResult(session_id=params.session_id)


@turn_channel.method("finish")
async def finish_turn(
    params: SessionParams,
    turn_service: Inject[TurnService],
) -> TurnCommandResult:
    await turn_service.finish(params.session_id)
    return TurnCommandResult(session_id=params.session_id)


@turn_channel.method("cancel", raises=(NO_ACTIVE_TURN,))
async def cancel_turn(
    params: SessionParams,
    turn_service: Inject[TurnService],
) -> TurnCommandResult:
    await turn_service.cancel(params.session_id)
    return TurnCommandResult(session_id=params.session_id)
