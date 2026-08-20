from dishka import Provider, Scope, provide
from fastapi import WebSocket

from gateway.features.conversation.application import ConversationService, EventBroker
from gateway.presentation.gateway_connection import GatewayConnection


class GatewayProvider(Provider):
    @provide(scope=Scope.SESSION)
    def connection(
        self,
        websocket: WebSocket,
        service: ConversationService,
        broker: EventBroker,
    ) -> GatewayConnection:
        return GatewayConnection(websocket, service, broker)
