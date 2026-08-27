from gateway.features.conversation.application import ConversationService
from gateway.features.conversation.presentation.rpc import (
    ConversationRpcMethod,
    SessionParams,
    StartTurnParams,
    TurnCommandResult,
)
from gateway.presentation import rpc
from gateway.presentation.rpc import (
    ResourceNotFoundError,
    RpcInternalError,
    RpcInvalidParamsError,
    TurnAlreadyRunningError,
)


class TurnRpcMethods(rpc.RpcHandler):
    def __init__(self, service: ConversationService) -> None:
        self._service = service

    @rpc.method(
        ConversationRpcMethod.TURN_PREPARE,
        summary="Prepare latency-sensitive resources for an upcoming turn.",
        errors=(ResourceNotFoundError, RpcInternalError),
    )
    async def prepare_turn(self, params: SessionParams) -> TurnCommandResult:
        await self._service.prepare_turn(params.session_id)
        return TurnCommandResult(session_id=params.session_id)

    @rpc.method(
        ConversationRpcMethod.TURN_START,
        summary="Start an agent turn in a conversation session.",
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

    @rpc.method(
        ConversationRpcMethod.TURN_FINISH,
        summary="Release resources prepared for a turn that is finished.",
        errors=(ResourceNotFoundError, RpcInternalError),
    )
    async def finish_turn(self, params: SessionParams) -> TurnCommandResult:
        await self._service.finish_turn(params.session_id)
        return TurnCommandResult(session_id=params.session_id)

    @rpc.method(
        ConversationRpcMethod.TURN_CANCEL,
        summary="Cancel the active turn in a conversation session.",
        errors=(
            RpcInvalidParamsError,
            ResourceNotFoundError,
            RpcInternalError,
        ),
    )
    async def cancel_turn(self, params: SessionParams) -> TurnCommandResult:
        await self._service.cancel_turn(params.session_id)
        return TurnCommandResult(session_id=params.session_id)
