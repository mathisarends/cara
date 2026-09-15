from sandbox_manager.features.health.application.ports import ReadinessCheck


class ReadinessService:
    def __init__(self, checks: list[ReadinessCheck]) -> None:
        self._checks = checks

    async def check(self) -> None:
        for readiness_check in self._checks:
            await readiness_check.check()
