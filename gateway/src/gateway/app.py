from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI

from gateway.container import create_container
from gateway.features import FEATURES
from gateway.infrastructure import DatabaseSettings, lifespan
from gateway.presentation import RequestLoggingMiddleware, health_router

_API_PREFIX = "/v1"


def create_app(settings: DatabaseSettings) -> FastAPI:
    app = FastAPI(
        title="Cara Gateway API",
        summary="JSON-RPC conversation gateway for Cara clients.",
        description=(
            "Commands, responses, and live events share one typed, long-lived "
            "WebSocket connection at /v1/conversation."
        ),
        version="0.1.0",
        lifespan=lifespan,
        openapi_tags=[
            {"name": "system", "description": "Gateway availability."},
            {"name": "sessions", "description": "Conversation session lifecycle."},
        ],
    )
    app.add_middleware(RequestLoggingMiddleware)
    app.include_router(health_router, prefix=_API_PREFIX)
    for feature in FEATURES:
        feature.install(app)

    setup_dishka(
        create_container(settings),
        app=app,
    )
    return app


app = create_app(DatabaseSettings())
