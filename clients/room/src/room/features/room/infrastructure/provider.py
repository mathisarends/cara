from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide

from room.features.health.application import ReadinessService
from room.features.room.application import (
    GatewayLink,
    GatewayRegistry,
    RegistrationService,
    ReportingService,
    RoomConnector,
)
from room.features.room.domain import Room
from room.features.room.infrastructure.gateway import (
    GatewayRoomConnector,
    GatewayRoomRegistry,
)
from room.platform import RoomConfig


class RoomProvider(Provider):
    @provide(scope=Scope.APP)
    def room(self, config: RoomConfig, readiness: ReadinessService) -> Room:
        devices = config.build_devices()
        room = Room(config.room_id, devices)
        readiness.devices_initialized()
        return room

    @provide(scope=Scope.APP)
    async def registry(self, config: RoomConfig) -> AsyncIterator[GatewayRoomRegistry]:
        registry = GatewayRoomRegistry(
            config.gateway.url,
            token=config.gateway.token,
        )
        try:
            yield registry
        finally:
            await registry.close()

    @provide(scope=Scope.APP)
    def registry_port(self, registry: GatewayRoomRegistry) -> GatewayRegistry:
        return registry

    @provide(scope=Scope.APP)
    def connector(self, config: RoomConfig) -> GatewayRoomConnector:
        gateway = config.gateway
        return GatewayRoomConnector(
            gateway.url,
            config.room_id,
            token=gateway.token,
            heartbeat_seconds=gateway.heartbeat_seconds,
        )

    @provide(scope=Scope.APP)
    def connector_port(self, connector: GatewayRoomConnector) -> RoomConnector:
        return connector

    @provide(scope=Scope.APP)
    def reporting(self, room: Room) -> ReportingService:
        return ReportingService(room)

    @provide(scope=Scope.APP)
    def registration(
        self,
        room: Room,
        registry: GatewayRegistry,
        readiness: ReadinessService,
    ) -> RegistrationService:
        return RegistrationService(room, registry, readiness)

    @provide(scope=Scope.APP)
    def link(
        self,
        room: Room,
        registration: RegistrationService,
        connector: RoomConnector,
        reporting: ReportingService,
        readiness: ReadinessService,
    ) -> GatewayLink:
        return GatewayLink(
            room,
            registration,
            connector,
            reporting,
            readiness,
        )
