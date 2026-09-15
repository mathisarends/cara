from fastapi import FastAPI
from fastapi_canon import Composition, ErrorOptions

from sandbox_manager.features import FEATURES
from sandbox_manager.platform import platform_feature


def create_app() -> FastAPI:
    app = FastAPI(
        title="Cara Sandbox Manager",
        version="1",
        openapi_tags=[
            {"name": "system", "description": "Sandbox Manager availability."},
            {
                "name": "sandboxes",
                "description": "Workspace sandbox lifecycle and command execution.",
            },
            {"name": "files", "description": "Workspace filesystem access."},
        ],
    )
    composition = Composition(
        platform_feature,
        *FEATURES,
        errors=ErrorOptions(type_base="urn:cara:sandbox-manager:problem"),
    )
    composition.apply(app)
    return app
