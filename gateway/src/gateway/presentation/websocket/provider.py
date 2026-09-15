import uuid

import pyrpckit as rpc
from dishka import AsyncContainer, Provider, Scope, provide
from fastapi import WebSocket
from pyrpckit.dishka import DishkaResolver

from gateway.features.conversation.application import EventPublisher, SessionService
from gateway.presentation.authentication import (
    GatewayAuthenticator,
    GatewayAuthSettings,
)
from gateway.presentation.websocket.connection import GatewayConnection
from gateway.presentation.websocket.error_mapping import gateway_error_mapper
from gateway.presentation.websocket.subscriptions import (
    EventStreamRpcMethods,
    GatewayClient,
    InMemoryEventStream,
)


class GatewayProvider(Provider):
    def __init__(self, channel: rpc.RpcChannel) -> None:
        super().__init__()
        self._channel = channel

    @provide(scope=Scope.APP)
    def auth_settings(self) -> GatewayAuthSettings:
        return GatewayAuthSettings()

    @provide(scope=Scope.APP)
    def authenticator(
        self,
        settings: GatewayAuthSettings,
    ) -> GatewayAuthenticator:
        return GatewayAuthenticator(settings)

    @provide(scope=Scope.APP)
    def event_stream(self) -> InMemoryEventStream:
        return InMemoryEventStream()

    @provide(scope=Scope.APP)
    def event_publisher(self, stream: InMemoryEventStream) -> EventPublisher:
        return stream

    @provide(scope=Scope.SESSION)
    def client(self) -> GatewayClient:
        client_id = str(uuid.uuid4())
        return GatewayClient(client_id)

    @provide(scope=Scope.SESSION)
    def rpc_methods(
        self,
        sessions: SessionService,
        stream: InMemoryEventStream,
        client: GatewayClient,
    ) -> EventStreamRpcMethods:
        return EventStreamRpcMethods(sessions, stream, client)

    @provide(scope=Scope.SESSION)
    def connection(
        self,
        container: AsyncContainer,
        websocket: WebSocket,
        authenticator: GatewayAuthenticator,
        stream: InMemoryEventStream,
        client: GatewayClient,
    ) -> GatewayConnection:
        authenticator.authenticate(websocket)
        server = self._channel.server(
            resolver=DishkaResolver(container),
            error_mapper=gateway_error_mapper,
        )
        return GatewayConnection(websocket, stream, client.id, server)
