from fastapi_canon import Feature

from sandbox_manager.features.files.infrastructure import FilesProvider
from sandbox_manager.features.files.presentation import files_router

feature = Feature(
    name="files",
    routers=[files_router],
    providers=[FilesProvider],
)
