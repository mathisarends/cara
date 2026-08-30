import pyrpckit as rpc

from gateway.features.conversation.application import SessionService, TurnService
from gateway.features.conversation.domain import ChannelRef
from gateway.features.conversation.presentation.rpc.mapping import (
    session_response,
    session_snapshot,
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
from gateway.presentation.rpc import (
    NoActiveTurnError,
    ResourceNotFoundError,
    TurnAlreadyRunningError,
)


class ConversationRpcMethods(rpc.RpcHandler):
    def __init__(
        self,
        sessions: SessionService,
        turns: TurnService,
    ) -> None:
        self._sessions = sessions
        self._turns = turns

    @rpc.method(
        ConversationRpcMethod.SESSION_CREATE,
        errors=(rpc.RpcInvalidParamsError, rpc.RpcInternalError),
    )
    async def create_session(self, params: CreateSessionParams) -> SessionResponse:
        session = await self._sessions.create(
            channel=_channel_ref(params),
            metadata=params.metadata,
        )
        return session_response(session)

    @rpc.method(
        ConversationRpcMethod.SESSION_OPEN,
        errors=(rpc.RpcInvalidParamsError, rpc.RpcInternalError),
    )
    async def open_session(self, params: OpenSessionParams) -> SessionResponse:
        session = await self._sessions.open(
            channel=_channel_ref(params),
            metadata=params.metadata,
        )
        return session_response(session)

    @rpc.method(
        ConversationRpcMethod.SESSION_GET,
        errors=(ResourceNotFoundError, rpc.RpcInternalError),
    )
    async def get_session(self, params: SessionParams) -> SessionSnapshotResponse:
        session = await self._sessions.get(params.session_id)
        return session_snapshot(session)

    @rpc.method(
        ConversationRpcMethod.TURN_PREPARE,
        errors=(ResourceNotFoundError, rpc.RpcInternalError),
    )
    async def prepare_turn(self, params: SessionParams) -> TurnCommandResult:
        await self._turns.prepare(params.session_id)
        return TurnCommandResult(session_id=params.session_id)

    @rpc.method(
        ConversationRpcMethod.TURN_START,
        errors=(
            rpc.RpcInvalidParamsError,
            ResourceNotFoundError,
            TurnAlreadyRunningError,
            rpc.RpcInternalError,
        ),
    )
    async def start_turn(self, params: StartTurnParams) -> TurnCommandResult:
        await self._turns.start(
            session_id=params.session_id,
            text=params.message,
            metadata=params.metadata,
        )
        return TurnCommandResult(session_id=params.session_id)

    @rpc.method(
        ConversationRpcMethod.TURN_STEER,
        errors=(
            rpc.RpcInvalidParamsError,
            ResourceNotFoundError,
            NoActiveTurnError,
            rpc.RpcInternalError,
        ),
    )
    async def steer_turn(self, params: SteerTurnParams) -> TurnCommandResult:
        await self._turns.steer(
            session_id=params.session_id,
            text=params.message,
        )
        return TurnCommandResult(session_id=params.session_id)

    @rpc.method(
        ConversationRpcMethod.TURN_FINISH,
        errors=(ResourceNotFoundError, rpc.RpcInternalError),
    )
    async def finish_turn(self, params: SessionParams) -> TurnCommandResult:
        await self._turns.finish(params.session_id)
        return TurnCommandResult(session_id=params.session_id)

    @rpc.method(
        ConversationRpcMethod.TURN_CANCEL,
        errors=(
            ResourceNotFoundError,
            NoActiveTurnError,
            rpc.RpcInternalError,
        ),
    )
    async def cancel_turn(self, params: SessionParams) -> TurnCommandResult:
        await self._turns.cancel(params.session_id)
        return TurnCommandResult(session_id=params.session_id)


def _channel_ref(params: CreateSessionParams) -> ChannelRef:
    return ChannelRef(
        name=params.channel.name,
        account_id=params.channel.account_id,
    )
