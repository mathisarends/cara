import asyncio

from fastapi import WebSocket, WebSocketDisconnect
from pyrpckit import RpcFailure, RpcNotification, RpcParseError, RpcServer, RpcSuccess

from gateway.features.conversation.application import EventBroker
from gateway.features.conversation.presentation.mapping import session_event
from gateway.features.conversation.presentation.rpc import RpcNotificationMethod


class GatewayConnection:
    """Owns the single bidirectional protocol connection for a gateway client."""

    def __init__(
        self,
        socket: WebSocket,
        broker: EventBroker,
        client_id: str,
        server: RpcServer,
    ) -> None:
        self._socket = socket
        self._broker = broker
        self._client_id = client_id
        self._receiver = broker.connect(client_id)
        self._server = server
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
                    await self._send(self._server.failure(None, RpcParseError()))
                    continue
                await self._handle(raw_request)
        except WebSocketDisconnect:
            pass
        finally:
            events.cancel()
            await asyncio.gather(events, return_exceptions=True)
            self._broker.disconnect(self._client_id)

    async def _handle(self, raw_request: object) -> None:
        response = await self._server.handle(raw_request)
        if response is not None:
            await self._send(response)

    async def _forward_conversation_events(self) -> None:
        while True:
            event = await self._receiver.receive()
            await self._send(
                RpcNotification(
                    method=RpcNotificationMethod.SESSION_EVENT,
                    params=session_event(event),
                )
            )

    async def _send(self, message: RpcSuccess | RpcFailure | RpcNotification) -> None:
        async with self._send_lock:
            await self._socket.send_json(message.model_dump(mode="json"))
