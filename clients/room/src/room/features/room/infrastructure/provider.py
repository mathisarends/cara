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
    def room(
        self,
        room_config: RoomConfig,
        readiness_service: ReadinessService,
    ) -> Room:
        devices = room_config.build_devices()
        room = Room(room_config.room_id, devices)
        readiness_service.devices_initialized()
        return room

    @provide(scope=Scope.APP)
    async def gateway_registry(
        self,
        room_config: RoomConfig,
    ) -> AsyncIterator[GatewayRoomRegistry]:
        gateway_registry = GatewayRoomRegistry(
            room_config.gateway.url,
            gateway_token=room_config.gateway.token,
        )
        try:
            yield gateway_registry
        finally:
            await gateway_registry.close()

    @provide(scope=Scope.APP)
    def gateway_registry_port(
        self,
        gateway_registry: GatewayRoomRegistry,
    ) -> GatewayRegistry:
        return gateway_registry

    @provide(scope=Scope.APP)
    def room_connector(self, room_config: RoomConfig) -> GatewayRoomConnector:
        gateway_config = room_config.gateway
        return GatewayRoomConnector(
            gateway_config.url,
            room_config.room_id,
            gateway_token=gateway_config.token,
            heartbeat_seconds=gateway_config.heartbeat_seconds,
        )

    @provide(scope=Scope.APP)
    def room_connector_port(
        self,
        room_connector: GatewayRoomConnector,
    ) -> RoomConnector:
        return room_connector

    @provide(scope=Scope.APP)
    def reporting_service(self, room: Room) -> ReportingService:
        return ReportingService(room)

    @provide(scope=Scope.APP)
    def registration_service(
        self,
        room: Room,
        gateway_registry: GatewayRegistry,
        readiness_service: ReadinessService,
    ) -> RegistrationService:
        return RegistrationService(room, gateway_registry, readiness_service)

    @provide(scope=Scope.APP)
    def gateway_link(
        self,
        room: Room,
        registration_service: RegistrationService,
        room_connector: RoomConnector,
        reporting_service: ReportingService,
        readiness_service: ReadinessService,
    ) -> GatewayLink:
        return GatewayLink(
            room,
            registration_service,
            room_connector,
            reporting_service,
            readiness_service,
        )
