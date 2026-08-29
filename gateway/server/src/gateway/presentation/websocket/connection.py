import asyncio

from fastapi import WebSocket, WebSocketDisconnect
from pyrpckit import RpcFailure, RpcNotification, RpcParseError, RpcServer, RpcSuccess

from gateway.presentation.websocket.event_forwarder import EventForwarder
from gateway.presentation.websocket.subscriptions import InMemoryEventStream


class GatewayConnection:
    """Owns the single bidirectional protocol connection for a gateway client."""

    def __init__(
        self,
        socket: WebSocket,
        stream: InMemoryEventStream,
        client_id: str,
        server: RpcServer,
    ) -> None:
        self._socket = socket
        self._stream = stream
        self._client_id = client_id
        self._receiver = stream.connect(client_id)
        self._server = server
        self._send_lock = asyncio.Lock()

    async def run(self) -> None:
        await self._socket.accept()
        forwarder = EventForwarder(self._receiver, self._send_notification)
        events = asyncio.create_task(forwarder.run(), name="gateway-events")
        try:
            while True:
                try:
                    raw_request = await self._socket.receive_json()
                except ValueError:
                    await self._send(self._server.failure(None, RpcParseError()))
                    continue
                await self._handle(raw_request)
        except WebSocketDisconnect:
            pass
        finally:
            events.cancel()
            await asyncio.gather(events, return_exceptions=True)
            self._stream.disconnect(self._client_id)

    async def _handle(self, raw_request: object) -> None:
        response = await self._server.handle(raw_request)
        if response is not None:
            await self._send(response)

    async def _send_notification(self, notification: RpcNotification) -> None:
        await self._send(notification)

    async def _send(self, message: RpcSuccess | RpcFailure | RpcNotification) -> None:
        async with self._send_lock:
            await self._socket.send_json(message.model_dump(mode="json"))
