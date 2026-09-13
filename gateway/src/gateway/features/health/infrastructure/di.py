from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncEngine

from gateway.features.health.application import ReadinessCheck, ReadinessService
from gateway.features.health.infrastructure.database import DatabaseReadinessCheck


class HealthProvider(Provider):
    scope = Scope.APP

    @provide
    def database_readiness_check(self, engine: AsyncEngine) -> DatabaseReadinessCheck:
        return DatabaseReadinessCheck(engine)

    @provide
    def readiness_checks(
        self, database: DatabaseReadinessCheck
    ) -> list[ReadinessCheck]:
        return [database]

    @provide
    def readiness_service(self, checks: list[ReadinessCheck]) -> ReadinessService:
        return ReadinessService(checks)
