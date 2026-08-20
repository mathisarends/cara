import asyncio
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from gateway.features.conversation.application import ConversationService, EventBroker
from gateway.features.conversation.domain import SessionBusyError, SessionNotFoundError
from gateway.features.conversation.presentation.mapping import session_event
from gateway.features.conversation.presentation.rpc import (
    CONVERSATION_REQUEST_ADAPTER,
    ConversationRequest,
    RpcErrorCode,
    RpcErrorData,
    RpcFailure,
    RpcNotification,
    RpcSchema,
    RpcSuccess,
)
from gateway.features.conversation.presentation.rpc_methods import (
    ConversationRpcMethods,
)


class _GatewayProtocolError(Exception):
    def __init__(self, code: RpcErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class GatewayConnection:
    """Owns the single bidirectional protocol connection for a gateway client."""

    def __init__(
        self,
        socket: WebSocket,
        service: ConversationService,
        broker: EventBroker,
    ) -> None:
        self._socket = socket
        self._broker = broker
        self._client_id = str(uuid4())
        self._receiver = broker.connect(self._client_id)
        self._conversation_methods = ConversationRpcMethods(
            service, broker, self._client_id
        )
        self._send_lock = asyncio.Lock()

    async def run(self) -> None:
        await self._socket.accept()
        events = asyncio.create_task(
            self._forward_conversation_events(), name="gateway-events"
        )
        try:
            while True:
                try:
                    raw_request = await self._socket.receive_json()
                except ValueError:
                    await self._send_error(
                        None, RpcErrorCode.PARSE_ERROR, "Parse error"
                    )
                    continue
                await self._handle(raw_request)
        except WebSocketDisconnect:
            pass
        finally:
            events.cancel()
            await asyncio.gather(events, return_exceptions=True)
            self._broker.disconnect(self._client_id)

    async def _handle(self, raw_request: object) -> None:
        request_id = _request_id(raw_request)
        try:
            request = _parse_request(raw_request)
            result = await self._conversation_methods.execute(request)
        except Exception as error:
            failure = _protocol_error(error)
            await self._send_error(request_id, failure.code, failure.message)
            return
        if request.expects_response:
            await self._send(RpcSuccess(id=request.id, result=result))

    async def _forward_conversation_events(self) -> None:
        while True:
            event = await self._receiver.receive()
            await self._send(RpcNotification(params=session_event(event)))

    async def _send_error(
        self, request_id: str | int | None, code: RpcErrorCode, message: str
    ) -> None:
        await self._send(
            RpcFailure(id=request_id, error=RpcErrorData(code=code, message=message))
        )

    async def _send(self, message: RpcSchema) -> None:
        async with self._send_lock:
            await self._socket.send_json(message.model_dump(mode="json"))


def _parse_request(raw_request: object) -> ConversationRequest:
    try:
        return CONVERSATION_REQUEST_ADAPTER.validate_python(raw_request)
    except ValidationError as error:
        raise _request_error(error) from error


def _request_error(error: ValidationError) -> _GatewayProtocolError:
    issue = error.errors(include_url=False)[0]
    if issue["type"] == "union_tag_invalid":
        return _GatewayProtocolError(RpcErrorCode.METHOD_NOT_FOUND, "Method not found")
    if "params" in issue["loc"]:
        location = ".".join(str(part) for part in issue["loc"])
        message = f"Invalid params at {location}: {issue['msg']}"
        return _GatewayProtocolError(RpcErrorCode.INVALID_PARAMS, message)
    return _GatewayProtocolError(RpcErrorCode.INVALID_REQUEST, "Invalid Request")


def _protocol_error(error: Exception) -> _GatewayProtocolError:
    if isinstance(error, _GatewayProtocolError):
        return error
    if isinstance(error, SessionNotFoundError):
        return _GatewayProtocolError(
            RpcErrorCode.RESOURCE_NOT_FOUND, f"Not found: {error}"
        )
    if isinstance(error, SessionBusyError):
        return _GatewayProtocolError(
            RpcErrorCode.TURN_ALREADY_RUNNING,
            f"Turn already running: {error}",
        )
    if isinstance(error, ValueError):
        return _GatewayProtocolError(
            RpcErrorCode.INVALID_PARAMS, f"Invalid params: {error}"
        )
    return _GatewayProtocolError(RpcErrorCode.INTERNAL_ERROR, "Internal error")


def _request_id(raw_request: object) -> str | int | None:
    if not isinstance(raw_request, dict):
        return None
    request_id = raw_request.get("id")
    if isinstance(request_id, str) or (
        isinstance(request_id, int) and not isinstance(request_id, bool)
    ):
        return request_id
    return None
