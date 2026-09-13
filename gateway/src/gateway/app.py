from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI

from gateway.container import create_container
from gateway.features import FEATURES
from gateway.lifespan import lifespan
from gateway.presentation import RequestLoggingMiddleware
from gateway.presentation.websocket.router import gateway_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Cara Gateway API",
        summary="JSON-RPC gateway for Cara clients.",
        description=(
            "Requests, commands, responses, and live events share one typed, "
            "long-lived WebSocket connection at /v1/gateway."
        ),
        version="0.1.0",
        lifespan=lifespan,
        openapi_tags=[
            {"name": "system", "description": "Gateway availability."},
            {"name": "gateway", "description": "Cara gateway protocol."},
            {"name": "sessions", "description": "Conversation session lifecycle."},
        ],
    )
    app.add_middleware(RequestLoggingMiddleware)
    app.include_router(gateway_router)
    for feature in FEATURES:
        feature.install(app)

    setup_dishka(
        create_container(),
        app=app,
    )
    return app


app = create_app()
