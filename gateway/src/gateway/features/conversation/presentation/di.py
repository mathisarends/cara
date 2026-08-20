from dishka import Provider, Scope, provide
from fastapi import WebSocket

from gateway.features.conversation.application import ConversationService, EventBroker
from gateway.features.conversation.presentation.socket import JsonRpcConnection


class ConversationSocketProvider(Provider):
    @provide(scope=Scope.SESSION)
    def connection(
        self,
        websocket: WebSocket,
        service: ConversationService,
        broker: EventBroker,
    ) -> JsonRpcConnection:
        return JsonRpcConnection(websocket, service, broker)
