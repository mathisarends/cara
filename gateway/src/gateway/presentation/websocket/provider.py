from uuid import uuid4

from dishka import Provider, Scope, provide
from fastapi import WebSocket

from gateway.features.automation.application import AutomationService
from gateway.features.automation.presentation import AutomationRpcMethods
from gateway.features.conversation.application import ConversationService, EventBroker
from gateway.features.conversation.presentation.session_rpc_methods import (
    SessionRpcMethods,
)
from gateway.features.conversation.presentation.subscription_rpc_methods import (
    SubscriptionRpcMethods,
)
from gateway.features.conversation.presentation.turn_rpc_methods import (
    TurnRpcMethods,
)
from gateway.presentation.websocket.connection import GatewayConnection
from gateway.presentation.websocket.error_mapping import gateway_error_mapper
from rpckit import RpcProtocol, RpcServer


class GatewayProvider(Provider):
    def __init__(self, protocol: RpcProtocol) -> None:
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
        session = SessionRpcMethods(service)
        subscription = SubscriptionRpcMethods(service, broker, client_id)
        turn = TurnRpcMethods(service)
        server = RpcServer(
            automation,
            session,
            subscription,
            turn,
            protocol=self._protocol,
            error_mapper=gateway_error_mapper,
        )
        return GatewayConnection(websocket, broker, client_id, server)
