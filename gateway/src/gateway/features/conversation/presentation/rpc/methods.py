from pyrpckit import Inject, RpcInternalError, RpcInvalidParamsError, RpcModule

from gateway.features.conversation.application import SessionService, TurnService
from gateway.features.conversation.domain import ChannelRef
from gateway.features.conversation.presentation.rpc.mapping import (
    session_response,
    session_snapshot,
)
from gateway.features.conversation.presentation.rpc.models import (
    ConversationRpcMethod,
    CreateSessionParams,
    OpenSessionParams,
    SessionChannel,
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
    sessions: Inject[SessionService],
) -> SessionResponse:
    session = await sessions.create(channel=_channel_ref(params.channel))
    return session_response(session)


@conversation_module.method(
    ConversationRpcMethod.SESSION_OPEN, errors=(RpcInvalidParamsError, RpcInternalError)
)
async def open_session(
    params: OpenSessionParams,
    sessions: Inject[SessionService],
) -> SessionResponse:
    session = await sessions.open(channel=_channel_ref(params.channel))
    return session_response(session)


@conversation_module.method(
    ConversationRpcMethod.SESSION_GET, errors=(ResourceNotFoundError, RpcInternalError)
)
async def get_session(
    params: SessionParams,
    sessions: Inject[SessionService],
) -> SessionSnapshotResponse:
    session = await sessions.get(params.session_id)
    return session_snapshot(session)


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


def _channel_ref(channel: SessionChannel) -> ChannelRef:
    return ChannelRef(channel.name)
