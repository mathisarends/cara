import logging
import time
from collections.abc import AsyncIterator

from dishka import Provider, Scope, from_context, provide
from fastapi_rpckit import RpcConnection

from gateway.features.conversation.application import (
    EventPublisher,
    EventSource,
)
from gateway.features.voice.application import VoiceEventPublisher
from gateway.presentation.authentication import (
    GatewayAuthenticator,
    GatewayAuthSettings,
)
from gateway.presentation.subscriptions import (
    EventReceiver,
    GatewayClient,
    InMemoryEventStream,
)
from gateway.rpc.sessions import GatewaySocketSession

logger = logging.getLogger(__name__)


class GatewayRpcProvider(Provider):
    connection = from_context(provides=RpcConnection, scope=Scope.SESSION)
    socket_session = from_context(GatewaySocketSession, scope=Scope.SESSION)

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

    @provide(scope=Scope.APP)
    def event_source(self, stream: InMemoryEventStream) -> EventSource:
        return stream

    @provide(scope=Scope.APP)
    def voice_event_publisher(
        self,
        stream: InMemoryEventStream,
    ) -> VoiceEventPublisher:
        return stream

    @provide(scope=Scope.SESSION)
    async def client(
        self,
        stream: InMemoryEventStream,
        connection: RpcConnection,
        socket_session: GatewaySocketSession,
    ) -> AsyncIterator[GatewayClient]:
        client_id = str(socket_session.connection_id)
        receiver = stream.connect(client_id)
        started = time.perf_counter()
        logger.info(
            "Gateway client %s connected from %s",
            _short_id(client_id),
            _remote_address(connection),
        )
        try:
            yield GatewayClient(client_id, receiver)
        finally:
            stream.disconnect(client_id)
            logger.info(
                "Gateway client %s disconnected (duration=%.1fms)",
                _short_id(client_id),
                (time.perf_counter() - started) * 1000,
            )

    @provide(scope=Scope.SESSION)
    def receiver(self, client: GatewayClient) -> EventReceiver:
        return client.receiver


def _remote_address(connection: RpcConnection) -> str:
    if connection.client is None:
        return "unknown"
    host, port = connection.client
    return f"{host}:{port}"


def _short_id(client_id: str) -> str:
    return client_id[:8]
