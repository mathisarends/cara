from dishka import Provider, Scope, provide

from sandbox_manager.features.files.application import (
    WorkspaceFileService,
    WorkspaceFileSystem,
)
from sandbox_manager.features.files.infrastructure.local import (
    LocalWorkspaceFileSystem,
)
from sandbox_manager.features.files.settings import FilesSettings


class FilesProvider(Provider):
    scope = Scope.APP

    @provide
    def settings(self) -> FilesSettings:
        return FilesSettings()

    @provide
    def file_system(self, settings: FilesSettings) -> WorkspaceFileSystem:
        return LocalWorkspaceFileSystem(settings.workspace_root)

    @provide
    def file_service(self, file_system: WorkspaceFileSystem) -> WorkspaceFileService:
        return WorkspaceFileService(file_system)
