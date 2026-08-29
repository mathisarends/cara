from pyrpckit import RpcHandler, RpcInternalError, RpcInvalidParamsError, method

from gateway.features.conversation.application import ConversationService
from gateway.features.conversation.presentation.rpc import (
    ConversationRpcMethod,
    SessionParams,
    StartTurnParams,
    TurnCommandResult,
)
from gateway.presentation.rpc import (
    ResourceNotFoundError,
    TurnAlreadyRunningError,
)


class TurnRpcMethods(RpcHandler):
    def __init__(self, service: ConversationService) -> None:
        self._service = service

    @method(
        ConversationRpcMethod.TURN_PREPARE,
        errors=(ResourceNotFoundError, RpcInternalError),
    )
    async def prepare_turn(self, params: SessionParams) -> TurnCommandResult:
        await self._service.prepare_turn(params.session_id)
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
        await self._service.start_turn(
            params.session_id,
            params.message,
            params.metadata,
        )
        return TurnCommandResult(session_id=params.session_id)

    @method(
        ConversationRpcMethod.TURN_FINISH,
        errors=(ResourceNotFoundError, RpcInternalError),
    )
    async def finish_turn(self, params: SessionParams) -> TurnCommandResult:
        await self._service.finish_turn(params.session_id)
        return TurnCommandResult(session_id=params.session_id)

    @method(
        ConversationRpcMethod.TURN_CANCEL,
        errors=(
            RpcInvalidParamsError,
            ResourceNotFoundError,
            RpcInternalError,
        ),
    )
    async def cancel_turn(self, params: SessionParams) -> TurnCommandResult:
        await self._service.cancel_turn(params.session_id)
        return TurnCommandResult(session_id=params.session_id)
