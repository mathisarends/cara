from uuid import uuid4

from dishka import Provider, Scope, provide
from fastapi import WebSocket

from gateway.features.automation.application import AutomationService
from gateway.features.automation.presentation import AutomationRpcMethods
from gateway.features.conversation.application import ConversationService, EventBroker
from gateway.features.conversation.presentation.rpc_methods import (
    ConversationRpcMethods,
)
from gateway.presentation.rpc.dispatch import GatewayRpcMethods
from gateway.presentation.rpc.protocol import GatewayProtocol
from gateway.presentation.websocket.connection import GatewayConnection


class GatewayProvider(Provider):
    def __init__(self, protocol: GatewayProtocol) -> None:
        super().__init__()
        self._protocol = protocol

    @provide(scope=Scope.SESSION)
    def connection(
        self,
        websocket: WebSocket,
        automation_service: AutomationService,
        service: ConversationService,
        broker: EventBroker,
    ) -> GatewayConnection:
        client_id = str(uuid4())
        automation = AutomationRpcMethods(automation_service)
        conversation = ConversationRpcMethods(service, broker, client_id)
        methods = GatewayRpcMethods(self._protocol, (automation, conversation))
        return GatewayConnection(websocket, broker, client_id, methods)
