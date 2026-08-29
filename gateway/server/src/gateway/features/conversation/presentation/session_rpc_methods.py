from pyrpckit import RpcHandler, RpcInternalError, RpcInvalidParamsError, method

from gateway.features.conversation.application import ConversationService
from gateway.features.conversation.domain import ChannelRef
from gateway.features.conversation.presentation.mapping import (
    session_response,
    session_snapshot,
)
from gateway.features.conversation.presentation.rpc import (
    ConversationRpcMethod,
    CreateSessionParams,
    OpenSessionParams,
    SessionParams,
)
from gateway.features.conversation.presentation.schemas import (
    SessionResponse,
    SessionSnapshotResponse,
)
from gateway.presentation.rpc import ResourceNotFoundError


class SessionRpcMethods(RpcHandler):
    def __init__(self, service: ConversationService) -> None:
        self._service = service

    @method(
        ConversationRpcMethod.SESSION_CREATE,
        summary="Create a conversation session.",
        errors=(RpcInvalidParamsError, RpcInternalError),
    )
    async def create_session(self, params: CreateSessionParams) -> SessionResponse:
        session = await self._service.create_session(
            _channel_ref(params),
            params.metadata,
        )
        return session_response(session)

    @method(
        ConversationRpcMethod.SESSION_OPEN,
        summary="Open the current session for a channel or create it.",
        errors=(RpcInvalidParamsError, RpcInternalError),
    )
    async def open_session(self, params: OpenSessionParams) -> SessionResponse:
        session = await self._service.open_session(
            _channel_ref(params),
            params.metadata,
        )
        return session_response(session)

    @method(
        ConversationRpcMethod.SESSION_GET,
        summary="Get a conversation session snapshot.",
        errors=(ResourceNotFoundError, RpcInternalError),
    )
    async def get_session(self, params: SessionParams) -> SessionSnapshotResponse:
        return session_snapshot(await self._service.get_session(params.session_id))


def _channel_ref(params: CreateSessionParams) -> ChannelRef:
    return ChannelRef(
        name=params.channel.name,
        account_id=params.channel.account_id,
    )
