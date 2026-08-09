from typing import Any

from fastapi import APIRouter, FastAPI

from gateway.features.conversation.presentation.schemas import event_adapter

schema_router = APIRouter(prefix="/v1/schemas", tags=["events"])


@schema_router.get(
    "/events",
    operation_id="get_event_schema",
    response_model=dict[str, Any],
    summary="Get the WebSocket event schema",
)
async def get_event_schema() -> dict[str, Any]:
    return event_adapter.json_schema()


def install_event_openapi(app: FastAPI) -> None:
    original_openapi = app.openapi

    def openapi() -> dict[str, Any]:
        document = original_openapi()
        event_schema = event_adapter.json_schema(
            ref_template="#/components/schemas/{model}"
        )
        definitions = event_schema.pop("$defs", {})
        schemas = document.setdefault("components", {}).setdefault("schemas", {})
        schemas.update(definitions)
        schemas["GatewayEventMessage"] = event_schema
        return document

    app.openapi = openapi
