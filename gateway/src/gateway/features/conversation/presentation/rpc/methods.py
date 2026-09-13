from pyrpckit import Inject, RpcInternalError, RpcInvalidParamsError, RpcModule

from gateway.features.conversation.presentation.rpc.handler import (
    ConversationRpcMethods,
)
from gateway.features.conversation.presentation.rpc.schemas import (
    ConversationRpcMethod,
    CreateSessionParams,
    OpenSessionParams,
    SessionParams,
    SessionResponse,
    SessionSnapshotResponse,
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
    ConversationRpcMethod.SESSION_CREATE,
    errors=(RpcInvalidParamsError, RpcInternalError),
)
async def create_session(
    params: CreateSessionParams,
    handler: Inject[ConversationRpcMethods],
) -> SessionResponse:
    return await handler.create_session(params)


@conversation_module.method(
    ConversationRpcMethod.SESSION_OPEN, errors=(RpcInvalidParamsError, RpcInternalError)
)
async def open_session(
    params: OpenSessionParams,
    handler: Inject[ConversationRpcMethods],
) -> SessionResponse:
    return await handler.open_session(params)


@conversation_module.method(
    ConversationRpcMethod.SESSION_GET, errors=(ResourceNotFoundError, RpcInternalError)
)
async def get_session(
    params: SessionParams,
    handler: Inject[ConversationRpcMethods],
) -> SessionSnapshotResponse:
    return await handler.get_session(params)


@conversation_module.method(
    ConversationRpcMethod.TURN_PREPARE, errors=(ResourceNotFoundError, RpcInternalError)
)
async def prepare_turn(
    params: SessionParams,
    handler: Inject[ConversationRpcMethods],
) -> TurnCommandResult:
    return await handler.prepare_turn(params)


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
    handler: Inject[ConversationRpcMethods],
) -> TurnCommandResult:
    return await handler.start_turn(params)


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
    handler: Inject[ConversationRpcMethods],
) -> TurnCommandResult:
    return await handler.steer_turn(params)


@conversation_module.method(
    ConversationRpcMethod.TURN_FINISH, errors=(ResourceNotFoundError, RpcInternalError)
)
async def finish_turn(
    params: SessionParams,
    handler: Inject[ConversationRpcMethods],
) -> TurnCommandResult:
    return await handler.finish_turn(params)


@conversation_module.method(
    ConversationRpcMethod.TURN_CANCEL,
    errors=(ResourceNotFoundError, NoActiveTurnError, RpcInternalError),
)
async def cancel_turn(
    params: SessionParams,
    handler: Inject[ConversationRpcMethods],
) -> TurnCommandResult:
    return await handler.cancel_turn(params)
