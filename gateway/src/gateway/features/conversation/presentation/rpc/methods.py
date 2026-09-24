from rpckit import Inject, RpcChannel

from gateway.features.conversation.application import TurnService
from gateway.features.conversation.presentation.rpc.models import (
    SessionParams,
    StartTurnParams,
    SteerTurnParams,
    TurnCommandResult,
)
from gateway.presentation.rpc.errors import (
    NoActiveTurnError,
    ResourceNotFoundError,
    TurnAlreadyRunningError,
)

turn_channel = RpcChannel("turn", raises=(ResourceNotFoundError,))


@turn_channel.server.method("prepare")
async def prepare_turn(
    params: SessionParams,
    turns: Inject[TurnService],
) -> TurnCommandResult:
    await turns.prepare(params.session_id)
    return TurnCommandResult(session_id=params.session_id)


@turn_channel.server.method("start", raises=(TurnAlreadyRunningError,))
async def start_turn(
    params: StartTurnParams,
    turns: Inject[TurnService],
) -> TurnCommandResult:
    await turns.start(
        session_id=params.session_id,
        text=params.message,
    )
    return TurnCommandResult(session_id=params.session_id)


@turn_channel.server.method("steer", raises=(NoActiveTurnError,))
async def steer_turn(
    params: SteerTurnParams,
    turns: Inject[TurnService],
) -> TurnCommandResult:
    await turns.steer(session_id=params.session_id, text=params.message)
    return TurnCommandResult(session_id=params.session_id)


@turn_channel.server.method("finish")
async def finish_turn(
    params: SessionParams,
    turns: Inject[TurnService],
) -> TurnCommandResult:
    await turns.finish(params.session_id)
    return TurnCommandResult(session_id=params.session_id)


@turn_channel.server.method("cancel", raises=(NoActiveTurnError,))
async def cancel_turn(
    params: SessionParams,
    turns: Inject[TurnService],
) -> TurnCommandResult:
    await turns.cancel(params.session_id)
    return TurnCommandResult(session_id=params.session_id)
