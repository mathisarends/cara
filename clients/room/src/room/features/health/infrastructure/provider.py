from dishka import Provider, Scope, provide

from room.features.health.application import ReadinessService


class HealthProvider(Provider):
    @provide(scope=Scope.APP)
    def readiness_service(self) -> ReadinessService:
        readiness_service = ReadinessService()
        readiness_service.config_loaded()
        return readiness_service
