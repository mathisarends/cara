from dishka import Provider, Scope, provide

from sandbox_manager.features.files.settings import FilesSettings
from sandbox_manager.features.health.application import (
    ReadinessCheck,
    ReadinessService,
)
from sandbox_manager.features.health.infrastructure.checks import (
    SandboxRuntimeReadinessCheck,
    WorkspaceReadinessCheck,
)
from sandbox_manager.features.sandbox.application import SandboxRuntime


class HealthProvider(Provider):
    scope = Scope.APP

    @provide
    def readiness_checks(
        self,
        runtime: SandboxRuntime,
        files_settings: FilesSettings,
    ) -> list[ReadinessCheck]:
        return [
            SandboxRuntimeReadinessCheck(runtime),
            WorkspaceReadinessCheck(files_settings.workspace_root),
        ]

    @provide
    def readiness_service(self, checks: list[ReadinessCheck]) -> ReadinessService:
        return ReadinessService(checks)
