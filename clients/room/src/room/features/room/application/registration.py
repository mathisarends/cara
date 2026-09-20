from room.features.health.application import ReadinessService
from room.features.room.application.ports import GatewayRegistry
from room.features.room.domain import Room


class RegistrationService:
    def __init__(
        self,
        room: Room,
        gateway_registry: GatewayRegistry,
        readiness_service: ReadinessService,
    ) -> None:
        self._room = room
        self._gateway_registry = gateway_registry
        self._readiness_service = readiness_service

    async def register(self) -> None:
        self._readiness_service.gateway_registered(False)
        await self._gateway_registry.register(self._room)
        self._readiness_service.gateway_registered(True)
