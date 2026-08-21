from gateway.features.conversation.application import ConversationService
from gateway.features.conversation.presentation.rpc import (
    ConversationRpcMethod,
    SessionParams,
    StartTurnParams,
    TurnCommandResult,
)
from gateway.presentation import rpc
from gateway.presentation.rpc import RpcErrorCode


class TurnRpcMethods(rpc.RpcHandler):
    def __init__(self, service: ConversationService) -> None:
        self._service = service

    @rpc.method(
        ConversationRpcMethod.TURN_START,
        summary="Start an agent turn in a conversation session.",
        errors=(
            RpcErrorCode.INVALID_PARAMS,
            RpcErrorCode.RESOURCE_NOT_FOUND,
            RpcErrorCode.TURN_ALREADY_RUNNING,
            RpcErrorCode.INTERNAL_ERROR,
        ),
    )
    async def start_turn(self, params: StartTurnParams) -> TurnCommandResult:
        await self._service.start_turn(
            params.session_id,
            params.message,
            params.metadata,
        )
        return TurnCommandResult(session_id=params.session_id)

    @rpc.method(
        ConversationRpcMethod.TURN_CANCEL,
        summary="Cancel the active turn in a conversation session.",
        errors=(
            RpcErrorCode.INVALID_PARAMS,
            RpcErrorCode.RESOURCE_NOT_FOUND,
            RpcErrorCode.INTERNAL_ERROR,
        ),
    )
    async def cancel_turn(self, params: SessionParams) -> TurnCommandResult:
        await self._service.cancel_turn(params.session_id)
        return TurnCommandResult(session_id=params.session_id)
