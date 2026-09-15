from fastapi import FastAPI
from fastapi_canon import Composition, ErrorOptions

from gateway.features import FEATURES
from gateway.lifespan import lifespan
from gateway.platform_feature import platform_feature
from gateway.presentation import RequestLoggingMiddleware


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
            {"name": "automations", "description": "Scheduled agent runs."},
        ],
    )
    app.add_middleware(RequestLoggingMiddleware)
    Composition(
        platform_feature,
        *FEATURES,
        errors=ErrorOptions(type_base="urn:cara:problem"),
    ).apply(app)
    return app


app = create_app()
