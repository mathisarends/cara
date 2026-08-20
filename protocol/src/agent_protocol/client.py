import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any, Protocol, Self
from uuid import UUID

from pydantic import TypeAdapter
from websockets.asyncio.client import ClientConnection, connect

from agent_protocol.events import SESSION_EVENT_ADAPTER, SessionEvent
from agent_protocol.models import Session, SessionSnapshot
from agent_protocol.rpc import (
    RpcMethod,
    RpcNotificationMethod,
    SubscriptionResult,
    TurnCommandResult,
    UnsubscriptionResult,
)


class WebSocketConnection(Protocol):
    async def send(self, message: str) -> None: ...
    async def close(self) -> None: ...
    def __aiter__(self) -> AsyncIterator[str | bytes]: ...


class RpcError(RuntimeError):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"JSON-RPC error {code}: {message}")
        self.code = code
        self.message = message


class JsonRpcClient:
    def __init__(self, socket: WebSocketConnection) -> None:
        self._socket = socket
        self._next_id = 1
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._events: asyncio.Queue[SessionEvent] = asyncio.Queue()
        self._receiver = asyncio.create_task(self._receive(), name="rpc-receiver")

    @classmethod
    async def connect(cls, url: str) -> Self:
        socket: ClientConnection = await connect(url)
        return cls(socket)

    async def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        request_id = self._next_id
        self._next_id += 1
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        request: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params is not None:
            request["params"] = params
        try:
            await self._socket.send(json.dumps(request))
            return await future
        finally:
            self._pending.pop(request_id, None)

    async def close(self) -> None:
        await self._socket.close()
        self._receiver.cancel()
        with suppress(asyncio.CancelledError):
            await self._receiver

    async def next_event(self) -> SessionEvent:
        return await self._events.get()

    async def events(self) -> AsyncIterator[SessionEvent]:
        while True:
            yield await self.next_event()

    async def _receive(self) -> None:
        try:
            async for raw_message in self._socket:
                message = json.loads(raw_message)
                if isinstance(message, dict):
                    await self._dispatch(message)
        except Exception as error:
            self._fail_pending(error)
        finally:
            self._fail_pending(ConnectionError("WebSocket closed"))

    async def _dispatch(self, message: dict[str, Any]) -> None:
        if "id" not in message:
            if message.get("method") == RpcNotificationMethod.SESSION_EVENT:
                await self._events.put(
                    SESSION_EVENT_ADAPTER.validate_python(message.get("params"))
                )
            return
        request_id = message.get("id")
        future = self._pending.get(request_id)
        if future is None or future.done():
            return
        if "error" in message:
            error = message["error"]
            future.set_exception(RpcError(error["code"], error["message"]))
        else:
            future.set_result(message.get("result"))

    def _fail_pending(self, error: BaseException) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(error)


class ConversationClient:
    def __init__(self, rpc: JsonRpcClient) -> None:
        self._rpc = rpc

    @classmethod
    async def connect(cls, url: str = "ws://127.0.0.1:8000/v1/conversation") -> Self:
        return cls(await JsonRpcClient.connect(url))

    async def close(self) -> None:
        await self._rpc.close()

    async def create_session(
        self, metadata: dict[str, object] | None = None
    ) -> Session:
        result = await self._rpc.request(
            RpcMethod.SESSION_CREATE, {"metadata": metadata or {}}
        )
        return TypeAdapter(Session).validate_python(result)

    async def get_session(self, session_id: UUID) -> SessionSnapshot:
        result = await self._rpc.request(
            RpcMethod.SESSION_GET, {"session_id": str(session_id)}
        )
        return TypeAdapter(SessionSnapshot).validate_python(result)

    async def subscribe(self, session_id: UUID) -> SubscriptionResult:
        result = await self._rpc.request(
            RpcMethod.SESSION_SUBSCRIBE, {"session_id": str(session_id)}
        )
        return TypeAdapter(SubscriptionResult).validate_python(result)

    async def unsubscribe(self, session_id: UUID) -> UnsubscriptionResult:
        result = await self._rpc.request(
            RpcMethod.SESSION_UNSUBSCRIBE, {"session_id": str(session_id)}
        )
        return TypeAdapter(UnsubscriptionResult).validate_python(result)

    async def start_turn(
        self,
        session_id: UUID,
        message: str,
        metadata: dict[str, object] | None = None,
    ) -> TurnCommandResult:
        result = await self._rpc.request(
            RpcMethod.TURN_START,
            {
                "session_id": str(session_id),
                "message": message,
                "metadata": metadata or {},
            },
        )
        return TypeAdapter(TurnCommandResult).validate_python(result)

    async def cancel_turn(self, session_id: UUID) -> TurnCommandResult:
        result = await self._rpc.request(
            RpcMethod.TURN_CANCEL, {"session_id": str(session_id)}
        )
        return TypeAdapter(TurnCommandResult).validate_python(result)

    def events(self) -> AsyncIterator[SessionEvent]:
        return self._rpc.events()

    async def next_event(self) -> SessionEvent:
        return await self._rpc.next_event()
