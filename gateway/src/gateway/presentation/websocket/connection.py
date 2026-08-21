import asyncio

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from gateway.features.automation.domain import AutomationNotFoundError
from gateway.features.conversation.application import EventBroker
from gateway.features.conversation.domain import SessionBusyError, SessionNotFoundError
from gateway.features.conversation.presentation.mapping import session_event
from gateway.features.conversation.presentation.rpc import RpcNotificationMethod
from gateway.presentation.rpc.dispatch import GatewayRpcMethods, RpcInvalidParamsError
from gateway.presentation.rpc.envelopes import (
    RpcErrorCode,
    RpcErrorData,
    RpcFailure,
    RpcNotification,
    RpcSchema,
    RpcSuccess,
)
from gateway.presentation.rpc.protocol import RpcMethodNotFoundError


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
        broker: EventBroker,
        client_id: str,
        methods: GatewayRpcMethods,
    ) -> None:
        self._socket = socket
        self._broker = broker
        self._client_id = client_id
        self._receiver = broker.connect(client_id)
        self._methods = methods
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
            invocation = self._methods.parse_request(raw_request)
            result = await self._methods.execute(invocation)
        except Exception as error:
            failure = _protocol_error(error)
            await self._send_error(request_id, failure.code, failure.message)
            return
        if invocation.request.expects_response:
            await self._send(RpcSuccess(id=invocation.request.id, result=result))

    async def _forward_conversation_events(self) -> None:
        while True:
            event = await self._receiver.receive()
            await self._send(
                RpcNotification(
                    method=RpcNotificationMethod.SESSION_EVENT,
                    params=session_event(event),
                )
            )

    async def _send_error(
        self, request_id: str | int | None, code: RpcErrorCode, message: str
    ) -> None:
        await self._send(
            RpcFailure(id=request_id, error=RpcErrorData(code=code, message=message))
        )

    async def _send(self, message: RpcSchema) -> None:
        async with self._send_lock:
            await self._socket.send_json(message.model_dump(mode="json"))


def _request_error(error: ValidationError) -> _GatewayProtocolError:
    issue = error.errors(include_url=False)[0]
    if "params" in issue["loc"]:
        location = ".".join(str(part) for part in issue["loc"])
        message = f"Invalid params at {location}: {issue['msg']}"
        return _GatewayProtocolError(RpcErrorCode.INVALID_PARAMS, message)
    return _GatewayProtocolError(RpcErrorCode.INVALID_REQUEST, "Invalid Request")


def _protocol_error(error: Exception) -> _GatewayProtocolError:
    if isinstance(error, _GatewayProtocolError):
        return error
    if isinstance(error, RpcMethodNotFoundError):
        return _GatewayProtocolError(RpcErrorCode.METHOD_NOT_FOUND, "Method not found")
    if isinstance(error, RpcInvalidParamsError):
        return _GatewayProtocolError(RpcErrorCode.INVALID_PARAMS, error.message)
    if isinstance(error, ValidationError):
        return _request_error(error)
    if isinstance(error, SessionNotFoundError | AutomationNotFoundError):
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
