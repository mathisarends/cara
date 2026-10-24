from fastapi import APIRouter, Depends, FastAPI
from fastapi_canon import Composition, ErrorOptions

from gateway.composition import FEATURES
from gateway.platform.api import API_PREFIX, http_request_scope
from gateway.platform.feature import platform_feature
from gateway.platform.observability import Telemetry, TelemetrySettings
from gateway.presentation import RequestLoggingMiddleware
from gateway.rpc.feature import feature as rpc_feature


def create_app() -> FastAPI:
    request_scope = Depends(http_request_scope, scope="function")
    app = FastAPI(
        dependencies=[request_scope],
        title="Cara Gateway API",
        summary="REST resources and a JSON-RPC WebSocket for Cara clients.",
        description=(
            "Resources such as sessions, automations, and alarms are plain REST. "
            "Commands and events of a live conversation share one JSON-RPC "
            "WebSocket connection at /v1/gateway."
        ),
        version="0.1.0",
        openapi_tags=[
            {"name": "system", "description": "Gateway availability."},
            {"name": "gateway", "description": "Cara gateway protocol."},
            {"name": "sessions", "description": "Conversation session lifecycle."},
            {"name": "automations", "description": "Scheduled agent runs."},
            {"name": "alarms", "description": "Wake-up alarms with agentic routines."},
            {"name": "voice", "description": "Persistent voice and media sessions."},
            {"name": "rooms", "description": "Room topology and live device state."},
        ],
    )
    app.add_middleware(RequestLoggingMiddleware)
    error_options = ErrorOptions(type_base="urn:cara:problem")
    composition = Composition(
        platform_feature,
        *FEATURES,
        rpc_feature,
        errors=error_options,
        router_factory=_api_router,
    )
    composition.apply(app)
    telemetry_settings = TelemetrySettings()
    telemetry = Telemetry(telemetry_settings)
    telemetry.install(app)
    app.state.telemetry = telemetry
    return app


def _api_router() -> APIRouter:
    return APIRouter(prefix=API_PREFIX)


app = create_app()
