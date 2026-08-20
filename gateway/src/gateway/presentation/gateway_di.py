from uuid import uuid4

from dishka import Provider, Scope, provide
from fastapi import WebSocket

from gateway.features.conversation.application import ConversationService, EventBroker
from gateway.features.conversation.presentation.rpc_methods import (
    ConversationRpcMethods,
)
from gateway.presentation.gateway_connection import GatewayConnection
from gateway.presentation.protocol import GatewayProtocol
from gateway.presentation.rpc_methods import GatewayRpcMethods


class GatewayProvider(Provider):
    def __init__(self, protocol: GatewayProtocol) -> None:
        super().__init__()
        self._protocol = protocol

    @provide(scope=Scope.SESSION)
    def connection(
        self,
        websocket: WebSocket,
        service: ConversationService,
        broker: EventBroker,
    ) -> GatewayConnection:
        client_id = str(uuid4())
        conversation = ConversationRpcMethods(service, broker, client_id)
        methods = GatewayRpcMethods(self._protocol, conversation.bindings())
        return GatewayConnection(websocket, broker, client_id, methods)
