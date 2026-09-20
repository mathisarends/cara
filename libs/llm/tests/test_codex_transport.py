from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from openai import AsyncOpenAI
from openai.types.responses import ResponseCompletedEvent
from openai.types.responses.responses_server_event import ResponseWsError
from pydantic_ai.providers.openai_codex import OpenAICodexProvider

from llm.codex_transport import (
    CodexResponsesResource,
    WebSocketInterrupted,
    WebSocketUnavailable,
)


async def test_websocket_error_before_response_creation_allows_http_fallback() -> None:
    error = ResponseWsError(
        type="error",
        status=400,
        error={
            "type": "invalid_request_error",
            "code": "previous_response_not_found",
            "message": "Previous response was not found",
            "param": "previous_response_id",
        },
    )
    connection = _connection(error)
    client, resource = _resource(connection)

    stream = await resource.create(
        model="gpt-5.6-sol",
        input="Question",
        stream=True,
    )
    with pytest.raises(WebSocketUnavailable):
        async with stream:
            await anext(stream)

    await client.close()


async def test_websocket_failure_after_response_creation_is_not_replayed() -> None:
    created = SimpleNamespace(type="response.created")
    connection = _connection(created, ConnectionError("connection lost"))
    client, resource = _resource(connection)

    stream = await resource.create(
        model="gpt-5.6-sol",
        input="Question",
        stream=True,
    )
    with pytest.raises(WebSocketInterrupted):
        async with stream:
            assert await anext(stream) is created
            await anext(stream)

    await client.close()


async def test_websocket_send_failure_allows_http_fallback() -> None:
    connection = _connection()
    connection.response.create.side_effect = ConnectionError("send failed")
    client, resource = _resource(connection)

    stream = await resource.create(
        model="gpt-5.6-sol",
        input="Question",
        stream=True,
    )
    with pytest.raises(WebSocketUnavailable):
        async with stream:
            pass

    await client.close()


async def test_non_streaming_request_returns_completed_websocket_response() -> None:
    response = SimpleNamespace(id="response-1")
    completed = ResponseCompletedEvent.model_construct(
        type="response.completed",
        sequence_number=1,
        response=response,
    )
    connection = _connection(completed)
    client, resource = _resource(connection)

    result = await resource.create(
        model="gpt-5.6-sol",
        input="Question",
        stream=False,
    )

    assert result is response
    await client.close()


async def test_websocket_request_removes_http_fields() -> None:
    error = ResponseWsError(
        type="error",
        status=400,
        error={
            "type": "invalid_request_error",
            "message": "stop",
        },
    )
    connection = _connection(error)
    client, resource = _resource(connection)

    stream = await resource.create(
        model="gpt-5.6-sol",
        input="Question",
        stream=True,
        background=False,
        extra_headers={"session-id": "session"},
        extra_body={"custom": "value"},
        timeout=10,
    )
    with pytest.raises(WebSocketUnavailable):
        async with stream:
            await anext(stream)

    connection.response.create.assert_awaited_once_with(
        model="gpt-5.6-sol",
        input="Question",
        custom="value",
        stream_id="main",
    )
    await client.close()


def _resource(connection: Any) -> tuple[AsyncOpenAI, CodexResponsesResource]:
    client = AsyncOpenAI(api_key="test")
    provider = cast(OpenAICodexProvider, object())
    resource = CodexResponsesResource(client, provider)
    resource._ensure_connection = AsyncMock(return_value=connection)
    return client, resource


def _connection(*events: object) -> SimpleNamespace:
    return SimpleNamespace(
        response=SimpleNamespace(create=AsyncMock()),
        recv=AsyncMock(side_effect=events),
    )
