from room.features.health.application import ReadinessService
from room.features.room.application.ports import GatewayRegistry
from room.features.room.domain import Room


class RegistrationService:
    def __init__(
        self,
        room: Room,
        registry: GatewayRegistry,
        readiness: ReadinessService,
    ) -> None:
        self._room = room
        self._registry = registry
        self._readiness = readiness

    async def register(self) -> None:
        self._readiness.gateway_registered(False)
        await self._registry.register(self._room)
        self._readiness.gateway_registered(True)
