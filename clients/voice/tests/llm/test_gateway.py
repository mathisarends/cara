import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import httpx2
import pytest

from gateway_rest_client import GatewayRestClient
from gateway_rpc_client import GatewayRpcClient
from gateway_rpc_client.models import SessionEventType
from voice.activation import PromptActivation
from voice.llm import (
    GatewayAgentSession,
    GatewayAgentTurnFailed,
    TextDelta,
    ToolCompleted,
    ToolStarted,
    TurnCompleted,
)
from voice.llm.gateway import _resolve_session


class _Transport:
    def __init__(self) -> None:
        self.session_id = uuid4()
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self._notifications: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def request(self, method: str, params: dict[str, Any]) -> Any:
        method_name = str(method)
        self.requests.append((method_name, params))
        if method_name == "subscription.subscribe":
            return {"subscribed": str(self.session_id)}
        if method_name == "subscription.unsubscribe":
            return {"unsubscribed": str(self.session_id)}
        if method_name in {
            "turn.prepare",
            "turn.start",
            "turn.finish",
            "turn.cancel",
        }:
            if method_name == "turn.cancel":
                await self.emit(SessionEventType.TURN_CANCELLED, sequence=100)
            return {"sessionId": str(self.session_id)}
        raise AssertionError(f"Unexpected method: {method_name}")

    async def notifications(self) -> AsyncIterator[dict[str, Any]]:
        while (notification := await self._notifications.get()) is not None:
            yield notification

    async def close(self) -> None:
        await self._notifications.put(None)

    async def emit(
        self,
        event_type: SessionEventType,
        *,
        sequence: int,
        **data: Any,
    ) -> None:
        await self._notifications.put(
            {
                "jsonrpc": "2.0",
                "method": "session.event",
                "params": {
                    "type": event_type,
                    "event_id": str(uuid4()),
                    "timestamp": datetime.now(UTC).isoformat(),
                    "session_id": str(self.session_id),
                    "sequence": sequence,
                    **data,
                },
            }
        )


async def _attach(transport: _Transport) -> GatewayAgentSession:
    return await GatewayAgentSession.attach(
        GatewayRpcClient(transport), transport.session_id
    )


def test_gateway_agent_session_translates_events() -> None:
    async def run() -> tuple[
        UUID,
        list[object],
        list[tuple[str, dict[str, Any]]],
    ]:
        transport = _Transport()
        session = await _attach(transport)
        await transport.emit(SessionEventType.CHAT_DELTA, sequence=1, text="Hallo ")
        await transport.emit(
            SessionEventType.TOOL_CALL_STARTED,
            sequence=2,
            call_id="call-1",
            name="weather",
            arguments={"city": "Berlin"},
        )
        await transport.emit(
            SessionEventType.TOOL_CALL_COMPLETED,
            sequence=3,
            call_id="call-1",
            name="weather",
            result={"temperature": 22},
            is_error=False,
        )
        await transport.emit(
            SessionEventType.CHAT_COMPLETED,
            sequence=4,
            text="Hallo Berlin",
            finish_reason="stop",
        )
        await transport.emit(SessionEventType.TURN_COMPLETED, sequence=5)

        await session.prepare_turn()
        stream = await session.start_turn("Wie ist das Wetter?")
        events = [event async for event in stream]
        await session.finish_turn()
        session_id = session.session_id
        await session.close()
        return session_id, events, transport.requests

    session_id, events, requests = asyncio.run(run())

    assert events == [
        TextDelta("Hallo "),
        ToolStarted("weather", "call-1", {"city": "Berlin"}),
        ToolCompleted("weather", "call-1", {"temperature": 22}),
        TurnCompleted("Hallo Berlin"),
    ]
    assert requests == [
        ("subscription.subscribe", {"sessionId": str(session_id)}),
        ("turn.prepare", {"sessionId": str(session_id)}),
        (
            "turn.start",
            {
                "sessionId": str(session_id),
                "message": "Wie ist das Wetter?",
                "metadata": {"modality": "voice"},
            },
        ),
        ("turn.finish", {"sessionId": str(session_id)}),
        ("subscription.unsubscribe", {"sessionId": str(session_id)}),
    ]


@pytest.mark.parametrize(
    ("new_session", "path"),
    [(False, "/v1/sessions/open"), (True, "/v1/sessions")],
)
def test_session_is_resolved_over_rest(new_session: bool, path: str) -> None:
    session_id = uuid4()
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(
            201 if new_session else 200,
            json={
                "id": str(session_id),
                "created_at": datetime.now(UTC).isoformat(),
                "channel": json.loads(request.content)["channel"],
            },
        )

    async def run() -> UUID:
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as http:
            sessions = GatewayRestClient(
                http, "http://gateway.test", credentials={"GatewayToken": "secret"}
            )
            return await _resolve_session(
                sessions, channel="voice", new_session=new_session
            )

    assert asyncio.run(run()) == session_id
    assert requests[0].url.path == path
    assert json.loads(requests[0].content) == {"channel": {"name": "voice"}}
    assert requests[0].headers["Authorization"] == "Bearer secret"


def test_server_started_turn_activates_voice_without_starting_a_second_turn() -> None:
    async def run() -> tuple[object, list[object], list[str]]:
        transport = _Transport()
        session = await _attach(transport)
        activations = session.activations()

        await transport.emit(
            SessionEventType.TURN_STARTED,
            sequence=1,
            metadata={"origin": "automation", "automation_kind": "reminder"},
        )
        activation = await anext(activations)
        await transport.emit(
            SessionEventType.CHAT_COMPLETED,
            sequence=2,
            text="Zeit aufzuwachen!",
            finish_reason="stop",
        )
        await transport.emit(SessionEventType.TURN_COMPLETED, sequence=3)

        stream = await session.start_turn(activation.prompt)
        events = [event async for event in stream]
        await activations.aclose()
        await session.close()
        return activation, events, [method for method, _ in transport.requests]

    activation, events, methods = asyncio.run(run())

    assert activation == PromptActivation(prompt="[Proactive gateway turn]")
    assert events == [
        TextDelta("Zeit aufzuwachen!"),
        TurnCompleted("Zeit aufzuwachen!"),
    ]
    assert methods == ["subscription.subscribe", "subscription.unsubscribe"]


def test_interrupt_cancels_the_active_gateway_turn_and_drains_its_terminal() -> None:
    async def run() -> list[str]:
        transport = _Transport()
        session = await _attach(transport)
        stream = await session.start_turn("Stop me")
        consuming = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        consuming.cancel()
        await asyncio.gather(consuming, return_exceptions=True)

        await session.interrupt()
        await session.close()
        return [method for method, _ in transport.requests]

    assert asyncio.run(run()) == [
        "subscription.subscribe",
        "turn.start",
        "turn.cancel",
        "subscription.unsubscribe",
    ]


def test_gateway_turn_failure_is_exposed_to_the_voice_bridge() -> None:
    async def run() -> None:
        transport = _Transport()
        session = await _attach(transport)
        await transport.emit(
            SessionEventType.TURN_FAILED,
            sequence=1,
            code="ModelError",
            message="model unavailable",
        )
        stream = await session.start_turn("Hello")

        with pytest.raises(GatewayAgentTurnFailed, match="model unavailable") as error:
            await anext(stream)

        assert error.value.code == "ModelError"
        await session.close()

    asyncio.run(run())
