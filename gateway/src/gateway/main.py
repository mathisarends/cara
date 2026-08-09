import uvicorn
from dishka import make_async_container
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI

from gateway.application import AgentRunner
from gateway.dependencies import GatewayProvider
from gateway.infrastructure import EchoAgentRunner
from gateway.lifespan import lifespan
from gateway.presentation import api_router, health_router

_API_PREFIX = "/v1"


def create_app(agent: AgentRunner | None = None) -> FastAPI:
    container = make_async_container(
        GatewayProvider(agent or EchoAgentRunner()),
        FastapiProvider(),
    )
    application = FastAPI(
        title="Cara Gateway API",
        summary="Session-based gateway for Cara clients.",
        description=(
            "Create and inspect sessions through HTTP. Send commands and receive "
            "run, chat, and tool-call events through the versioned WebSocket API."
        ),
        version="0.1.0",
        lifespan=lifespan,
        openapi_tags=[
            {"name": "system", "description": "Gateway availability."},
            {"name": "sessions", "description": "Conversation session lifecycle."},
        ],
    )
    application.include_router(health_router, prefix=_API_PREFIX)
    application.include_router(api_router, prefix=_API_PREFIX)
    setup_dishka(container, application)
    return application


app = create_app()


if __name__ == "__main__":
    uvicorn.run("gateway.main:app", reload=True)
