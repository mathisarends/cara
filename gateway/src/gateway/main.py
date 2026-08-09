import logging

import uvicorn
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI

from gateway.container import create_container
from gateway.features import FEATURES
from gateway.lifespan import lifespan
from gateway.presentation import health_router

_API_PREFIX = "/v1"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Cara Gateway API",
        summary="Session-based gateway for Cara clients.",
        description=(
            "Create and inspect sessions through HTTP. Send commands and receive "
            "turn, chat, and tool-call events through the versioned WebSocket API."
        ),
        version="0.1.0",
        lifespan=lifespan,
        openapi_tags=[
            {"name": "system", "description": "Gateway availability."},
            {"name": "sessions", "description": "Conversation session lifecycle."},
        ],
    )
    app.include_router(health_router, prefix=_API_PREFIX)
    for feature in FEATURES:
        feature.install(app)

    setup_dishka(
        create_container(),
        app=app,
    )
    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run("gateway.main:app", reload=True)
