import asyncio
import logging
import time

import pyrpckit as rpc
from fastapi import WebSocket, WebSocketDisconnect

from gateway.presentation.websocket.event_forwarder import EventForwarder
from gateway.presentation.websocket.subscriptions import InMemoryEventStream

logger = logging.getLogger(__name__)


class GatewayConnection:
    """Owns the single bidirectional protocol connection for a gateway client."""

    def __init__(
        self,
        socket: WebSocket,
        stream: InMemoryEventStream,
        client_id: str,
        server: rpc.RpcServer,
    ) -> None:
        self._socket = socket
        self._stream = stream
        self._client_id = client_id
        self._receiver = stream.connect(client_id)
        self._server = server
        self._send_lock = asyncio.Lock()

    async def run(self) -> None:
        await self._socket.accept()
        started = time.perf_counter()
        logger.info(
            "Gateway client %s connected from %s",
            _short_id(self._client_id),
            _remote_address(self._socket),
        )
        forwarder = EventForwarder(self._receiver, self._send_notification)
        events = asyncio.create_task(forwarder.run(), name="gateway-events")
        close_code = 1000
        try:
            while True:
                try:
                    raw_request = await self._socket.receive_json()
                except ValueError:
                    logger.warning(
                        "Gateway client %s sent malformed JSON",
                        _short_id(self._client_id),
                    )
                    await self._send(self._server.failure(None, rpc.RpcParseError()))
                    continue
                await self._handle(raw_request)
        except WebSocketDisconnect as disconnect:
            close_code = disconnect.code
        except Exception:
            close_code = 1011
            raise
        finally:
            events.cancel()
            await asyncio.gather(events, return_exceptions=True)
            self._stream.disconnect(self._client_id)
            logger.info(
                "Gateway client %s disconnected (code=%s, duration=%s)",
                _short_id(self._client_id),
                close_code,
                _elapsed(started),
            )

    async def _handle(self, raw_request: object) -> None:
        method, request_id = _request_identity(raw_request)
        started = time.perf_counter()
        response = await self._server.handle(raw_request)
        if response is not None:
            await self._send(response)
        logger.info(
            "RPC %s completed for client %s (id=%s, outcome=%s, duration=%s)",
            method,
            _short_id(self._client_id),
            request_id,
            _response_outcome(response),
            _elapsed(started),
        )

    async def _send_notification(self, notification: rpc.RpcNotification) -> None:
        await self._send(notification)

    async def _send(
        self,
        message: rpc.RpcSuccess | rpc.RpcFailure | rpc.RpcNotification,
    ) -> None:
        async with self._send_lock:
            await self._socket.send_json(message.model_dump(mode="json"))


def _request_identity(raw_request: object) -> tuple[str, object]:
    if not isinstance(raw_request, dict):
        return "<invalid>", None
    return str(raw_request.get("method", "<invalid>")), raw_request.get("id")


def _response_outcome(response: object) -> str:
    if response is None:
        return "notification"
    if isinstance(response, rpc.RpcFailure):
        return f"error:{response.error.code}"
    return "ok"


def _remote_address(socket: WebSocket) -> str:
    client = socket.client
    if client is None:
        return "unknown"
    return f"{client.host}:{client.port}"


def _short_id(client_id: str) -> str:
    return client_id[:8]


def _elapsed(started: float) -> str:
    return f"{(time.perf_counter() - started) * 1000:.1f}ms"
