from dishka import Provider, Scope, provide

from room.features.health.application import ReadinessService


class HealthProvider(Provider):
    @provide(scope=Scope.APP)
    def readiness(self) -> ReadinessService:
        readiness = ReadinessService()
        readiness.config_loaded()
        return readiness
