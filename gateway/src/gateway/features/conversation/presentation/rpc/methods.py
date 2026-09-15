from pyrpckit import Inject, RpcInternalError, RpcInvalidParamsError, RpcModule

from gateway.features.conversation.application import TurnService
from gateway.features.conversation.presentation.rpc.models import (
    ConversationRpcMethod,
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

conversation_module = RpcModule()


@conversation_module.method(
    ConversationRpcMethod.TURN_PREPARE, errors=(ResourceNotFoundError, RpcInternalError)
)
async def prepare_turn(
    params: SessionParams,
    turns: Inject[TurnService],
) -> TurnCommandResult:
    await turns.prepare(params.session_id)
    return TurnCommandResult(session_id=params.session_id)


@conversation_module.method(
    ConversationRpcMethod.TURN_START,
    errors=(
        RpcInvalidParamsError,
        ResourceNotFoundError,
        TurnAlreadyRunningError,
        RpcInternalError,
    ),
)
async def start_turn(
    params: StartTurnParams,
    turns: Inject[TurnService],
) -> TurnCommandResult:
    await turns.start(
        session_id=params.session_id,
        text=params.message,
        metadata=params.metadata,
    )
    return TurnCommandResult(session_id=params.session_id)


@conversation_module.method(
    ConversationRpcMethod.TURN_STEER,
    errors=(
        RpcInvalidParamsError,
        ResourceNotFoundError,
        NoActiveTurnError,
        RpcInternalError,
    ),
)
async def steer_turn(
    params: SteerTurnParams,
    turns: Inject[TurnService],
) -> TurnCommandResult:
    await turns.steer(session_id=params.session_id, text=params.message)
    return TurnCommandResult(session_id=params.session_id)


@conversation_module.method(
    ConversationRpcMethod.TURN_FINISH, errors=(ResourceNotFoundError, RpcInternalError)
)
async def finish_turn(
    params: SessionParams,
    turns: Inject[TurnService],
) -> TurnCommandResult:
    await turns.finish(params.session_id)
    return TurnCommandResult(session_id=params.session_id)


@conversation_module.method(
    ConversationRpcMethod.TURN_CANCEL,
    errors=(ResourceNotFoundError, NoActiveTurnError, RpcInternalError),
)
async def cancel_turn(
    params: SessionParams,
    turns: Inject[TurnService],
) -> TurnCommandResult:
    await turns.cancel(params.session_id)
    return TurnCommandResult(session_id=params.session_id)
