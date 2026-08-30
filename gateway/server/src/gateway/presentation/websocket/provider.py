import uuid

import pyrpckit as rpc
from dishka import Provider, Scope, provide
from fastapi import WebSocket

from gateway.features.automation.application import SessionAutomationService
from gateway.features.automation.presentation import AutomationRpcMethods
from gateway.features.conversation.application import (
    EventPublisher,
    SessionService,
    TurnService,
)
from gateway.features.conversation.presentation import ConversationRpcMethods
from gateway.presentation.websocket.authentication import (
    GatewayAuthenticator,
    GatewayAuthSettings,
)
from gateway.presentation.websocket.connection import GatewayConnection
from gateway.presentation.websocket.error_mapping import gateway_error_mapper
from gateway.presentation.websocket.subscriptions import (
    EventStreamRpcMethods,
    InMemoryEventStream,
)


class GatewayProvider(Provider):
    def __init__(self, protocol: rpc.RpcProtocol) -> None:
        super().__init__()
        self._protocol = protocol

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
    def connection(
        self,
        websocket: WebSocket,
        authenticator: GatewayAuthenticator,
        automation_service: SessionAutomationService,
        sessions: SessionService,
        turns: TurnService,
        stream: InMemoryEventStream,
    ) -> GatewayConnection:
        authenticator.authenticate(websocket)
        client_id = str(uuid.uuid4())
        server = rpc.RpcServer(
            AutomationRpcMethods(automation_service),
            ConversationRpcMethods(sessions, turns),
            EventStreamRpcMethods(sessions, stream, client_id),
            protocol=self._protocol,
            error_mapper=gateway_error_mapper,
        )
        return GatewayConnection(websocket, stream, client_id, server)
