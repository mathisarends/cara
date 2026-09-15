from collections.abc import AsyncIterator, Iterator

from dishka import Provider, Scope, provide

from sandbox_manager.features.sandbox.application import SandboxRuntime, SandboxService
from sandbox_manager.features.sandbox.infrastructure.docker import DockerSandboxRuntime
from sandbox_manager.features.sandbox.settings import SandboxSettings


class SandboxProvider(Provider):
    scope = Scope.APP

    @provide
    def settings(self) -> SandboxSettings:
        return SandboxSettings()

    @provide
    def runtime(self, settings: SandboxSettings) -> Iterator[SandboxRuntime]:
        runtime = DockerSandboxRuntime(settings)
        try:
            yield runtime
        finally:
            runtime.close()

    @provide
    async def sandbox_service(
        self,
        runtime: SandboxRuntime,
        settings: SandboxSettings,
    ) -> AsyncIterator[SandboxService]:
        service = SandboxService(runtime, settings)
        await service.start()
        try:
            yield service
        finally:
            await service.close()
