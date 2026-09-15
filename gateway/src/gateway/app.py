from fastapi import FastAPI
from fastapi_canon import Composition, ErrorOptions

from gateway.features import FEATURES
from gateway.lifespan import lifespan
from gateway.platform_feature import platform_feature
from gateway.presentation import RequestLoggingMiddleware


def create_app() -> FastAPI:
    app = FastAPI(
        title="Cara Gateway API",
        summary="REST resources and a JSON-RPC WebSocket for Cara clients.",
        description=(
            "Resources such as sessions, automations, and alarms are plain REST. "
            "Commands and events of a live conversation share one JSON-RPC "
            "WebSocket connection at /v1/gateway."
        ),
        version="0.1.0",
        lifespan=lifespan,
        openapi_tags=[
            {"name": "system", "description": "Gateway availability."},
            {"name": "gateway", "description": "Cara gateway protocol."},
            {"name": "sessions", "description": "Conversation session lifecycle."},
            {"name": "automations", "description": "Scheduled agent runs."},
            {"name": "alarms", "description": "Wake-up alarms with agentic routines."},
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
