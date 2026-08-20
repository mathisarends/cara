from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter

from agent_protocol.rpc import (
    CONVERSATION_PROTOCOL_ADAPTER,
    CONVERSATION_REQUEST_ADAPTER,
    CONVERSATION_SERVER_MESSAGE_ADAPTER,
)

schema_router = APIRouter(tags=["conversation schema"])


@schema_router.get(
    "/v1/conversation/schema",
    response_class=JSONResponse,
    summary="Conversation WebSocket JSON Schema",
)
async def conversation_schema() -> JSONResponse:
    return JSONResponse(
        CONVERSATION_PROTOCOL_ADAPTER.json_schema(mode="serialization"),
        media_type="application/schema+json",
    )


def install_protocol_openapi(app: FastAPI) -> None:
    document = app.openapi()
    schemas = document.setdefault("components", {}).setdefault("schemas", {})
    _add_schema(schemas, "ConversationRequest", CONVERSATION_REQUEST_ADAPTER)
    _add_schema(
        schemas, "ConversationServerMessage", CONVERSATION_SERVER_MESSAGE_ADAPTER
    )


def _add_schema(
    components: dict[str, Any], name: str, adapter: TypeAdapter[Any]
) -> None:
    schema = adapter.json_schema(
        mode="serialization", ref_template="#/components/schemas/{model}"
    )
    components.update(schema.pop("$defs", {}))
    components[name] = schema
