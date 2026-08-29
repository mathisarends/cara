from pyrpckit import RpcHandler, RpcInternalError, RpcInvalidParamsError, method

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
    TurnCommandResult,
)
from gateway.presentation.rpc import ResourceNotFoundError, TurnAlreadyRunningError


class ConversationRpcMethods(RpcHandler):
    def __init__(
        self,
        sessions: SessionService,
        turns: TurnService,
    ) -> None:
        self._sessions = sessions
        self._turns = turns

    @method(
        ConversationRpcMethod.SESSION_CREATE,
        errors=(RpcInvalidParamsError, RpcInternalError),
    )
    async def create_session(self, params: CreateSessionParams) -> SessionResponse:
        session = await self._sessions.create(
            channel=_channel_ref(params),
            metadata=params.metadata,
        )
        return session_response(session)

    @method(
        ConversationRpcMethod.SESSION_OPEN,
        errors=(RpcInvalidParamsError, RpcInternalError),
    )
    async def open_session(self, params: OpenSessionParams) -> SessionResponse:
        session = await self._sessions.open(
            channel=_channel_ref(params),
            metadata=params.metadata,
        )
        return session_response(session)

    @method(
        ConversationRpcMethod.SESSION_GET,
        errors=(ResourceNotFoundError, RpcInternalError),
    )
    async def get_session(self, params: SessionParams) -> SessionSnapshotResponse:
        session = await self._sessions.get(params.session_id)
        return session_snapshot(session)

    @method(
        ConversationRpcMethod.TURN_PREPARE,
        errors=(ResourceNotFoundError, RpcInternalError),
    )
    async def prepare_turn(self, params: SessionParams) -> TurnCommandResult:
        await self._turns.prepare(params.session_id)
        return TurnCommandResult(session_id=params.session_id)

    @method(
        ConversationRpcMethod.TURN_START,
        errors=(
            RpcInvalidParamsError,
            ResourceNotFoundError,
            TurnAlreadyRunningError,
            RpcInternalError,
        ),
    )
    async def start_turn(self, params: StartTurnParams) -> TurnCommandResult:
        await self._turns.start(
            session_id=params.session_id,
            text=params.message,
            metadata=params.metadata,
        )
        return TurnCommandResult(session_id=params.session_id)

    @method(
        ConversationRpcMethod.TURN_FINISH,
        errors=(ResourceNotFoundError, RpcInternalError),
    )
    async def finish_turn(self, params: SessionParams) -> TurnCommandResult:
        await self._turns.finish(params.session_id)
        return TurnCommandResult(session_id=params.session_id)

    @method(
        ConversationRpcMethod.TURN_CANCEL,
        errors=(RpcInvalidParamsError, ResourceNotFoundError, RpcInternalError),
    )
    async def cancel_turn(self, params: SessionParams) -> TurnCommandResult:
        await self._turns.cancel(params.session_id)
        return TurnCommandResult(session_id=params.session_id)


def _channel_ref(params: CreateSessionParams) -> ChannelRef:
    return ChannelRef(
        name=params.channel.name,
        account_id=params.channel.account_id,
    )
