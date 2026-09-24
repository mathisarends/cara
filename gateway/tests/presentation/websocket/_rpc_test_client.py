import asyncio
import json
from collections import deque
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Self

from rpckit import (
    RpcConnectionClose,
    RpcDisconnect,
    RpcHandshake,
    RpcRejection,
    RpcService,
)
from rpckit.dependencies import RpcResolverLike
from rpckit.server import RpcErrorMapper


class RpcTestError(Exception):
    def __init__(self, error: Mapping[str, Any]) -> None:
        data = error.get("data")
        payload = data if isinstance(data, dict) else {}
        self.rpc_code = error.get("code")
        self.code = payload.get("code")
        self.message = error.get("message")
        self.details = payload.get("details")
        super().__init__(self.message)


class RpcTestSocket:
    def __init__(self, path: str, headers: Mapping[str, str]) -> None:
        self._handshake = RpcHandshake(
            path=path,
            headers=MappingProxyType(dict(headers)),
        )
        self._incoming: asyncio.Queue[str | bytes | None] = asyncio.Queue()
        self._outgoing: asyncio.Queue[str | bytes | None] = asyncio.Queue()
        self._accepted = asyncio.Event()

    @property
    def handshake(self) -> RpcHandshake:
        return self._handshake

    async def accept(self, subprotocol: str | None = None) -> None:
        del subprotocol
        self._accepted.set()

    async def reject(self, rejection: RpcRejection, reason: str) -> None:
        del rejection, reason
        self._accepted.set()
        await self._outgoing.put(None)

    async def receive(self) -> str | bytes:
        message = await self._incoming.get()
        if message is None:
            raise RpcDisconnect()
        return message

    async def send(self, message: str) -> None:
        await self._outgoing.put(message)

    async def send_bytes(self, data: bytes) -> None:
        await self._outgoing.put(data)

    async def close(self, close: RpcConnectionClose, reason: str) -> None:
        del close, reason
        await self._outgoing.put(None)

    async def client_send(self, message: str | bytes) -> None:
        await self._incoming.put(message)

    async def client_receive(self) -> str | bytes:
        message = await self._outgoing.get()
        if message is None:
            raise RpcDisconnect()
        return message

    async def client_disconnect(self) -> None:
        await self._incoming.put(None)

    async def wait_until_accepted(self) -> None:
        await self._accepted.wait()


class RpcTestClient:
    def __init__(
        self,
        service: RpcService,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        resolver: RpcResolverLike | None = None,
        error_mapper: RpcErrorMapper | None = None,
    ) -> None:
        self._service = service
        self._resolver = resolver
        self._error_mapper = error_mapper
        self._socket = RpcTestSocket(path, headers or {})
        self._notifications: deque[tuple[str, Any]] = deque()
        self._next_id = 0
        self._server_task: asyncio.Task[None] | None = None

    @property
    def socket(self) -> RpcTestSocket:
        return self._socket

    async def __aenter__(self) -> Self:
        self._server_task = asyncio.create_task(
            self._service.serve(
                self._socket,
                resolver=self._resolver,
                error_mapper=self._error_mapper,
            )
        )
        await self._socket.wait_until_accepted()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self._socket.client_disconnect()
        if self._server_task is not None:
            await self._server_task

    async def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        self._next_id += 1
        request_id = self._next_id
        request: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params is not None:
            request["params"] = params
        await self._socket.client_send(json.dumps(request))
        while True:
            message = await self._receive_json()
            if "method" in message:
                self._notifications.append((message["method"], message.get("params")))
                continue
            if message.get("id") != request_id:
                continue
            error = message.get("error")
            if isinstance(error, dict):
                raise RpcTestError(error)
            return message.get("result")

    async def next_notification(self) -> tuple[str, Any]:
        if self._notifications:
            return self._notifications.popleft()
        while True:
            message = await self._receive_json()
            if "method" in message:
                return message["method"], message.get("params")

    async def _receive_json(self) -> dict[str, Any]:
        message = await self._socket.client_receive()
        if isinstance(message, bytes):
            message = message.decode()
        value = json.loads(message)
        if not isinstance(value, dict):
            raise TypeError("Expected a JSON-RPC object")
        return value
