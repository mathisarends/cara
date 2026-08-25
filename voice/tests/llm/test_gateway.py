import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from gateway_client import GatewayClient
from gateway_client.models import RpcMethod, SessionEventType
from voice.activation import PromptActivation
from voice.llm import (
    GatewayAgentSession,
    GatewayAgentTurnFailed,
    TextDelta,
    ToolCompleted,
    ToolStarted,
    TurnCompleted,
)


class _Transport:
    def __init__(self) -> None:
        self.session_id = uuid4()
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self._notifications: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def request(self, method: str, params: dict[str, Any]) -> Any:
        method_name = str(method)
        self.requests.append((method_name, params))
        if method_name in {RpcMethod.SESSION_OPEN, RpcMethod.SESSION_CREATE}:
            return {
                "id": str(self.session_id),
                "created_at": datetime.now(UTC).isoformat(),
                "channel": params["channel"],
                "metadata": params.get("metadata"),
            }
        if method_name == RpcMethod.SUBSCRIPTION_SUBSCRIBE:
            return {"subscribed": str(self.session_id)}
        if method_name == RpcMethod.SUBSCRIPTION_UNSUBSCRIBE:
            return {"unsubscribed": str(self.session_id)}
        if method_name in {RpcMethod.TURN_START, RpcMethod.TURN_CANCEL}:
            if method_name == RpcMethod.TURN_CANCEL:
                await self.emit(SessionEventType.TURN_CANCELLED, sequence=100)
            return {"session_id": str(self.session_id)}
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


def test_gateway_agent_session_reuses_channel_and_translates_events() -> None:
    async def run() -> tuple[
        UUID,
        list[object],
        list[tuple[str, dict[str, Any]]],
    ]:
        transport = _Transport()
        session = await GatewayAgentSession.attach(
            GatewayClient(transport),
            channel="voice",
            account_id="kitchen",
        )
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

        stream = await session.start_turn("Wie ist das Wetter?")
        events = [event async for event in stream]
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
        (
            "session.open",
            {
                "channel": {"name": "voice", "account_id": "kitchen"},
                "metadata": {"client": "cara-voice"},
            },
        ),
        ("subscription.subscribe", {"session_id": str(session_id)}),
        (
            "turn.start",
            {
                "session_id": str(session_id),
                "message": "Wie ist das Wetter?",
                "metadata": {"modality": "voice"},
            },
        ),
        ("subscription.unsubscribe", {"session_id": str(session_id)}),
    ]


def test_gateway_agent_session_can_explicitly_create_a_fresh_session() -> None:
    async def run() -> list[str]:
        transport = _Transport()
        session = await GatewayAgentSession.attach(
            GatewayClient(transport),
            new_session=True,
        )
        await session.close()
        return [method for method, _ in transport.requests]

    assert asyncio.run(run()) == [
        "session.create",
        "subscription.subscribe",
        "subscription.unsubscribe",
    ]


def test_server_started_turn_activates_voice_without_starting_a_second_turn() -> None:
    async def run() -> tuple[object, list[object], list[str]]:
        transport = _Transport()
        session = await GatewayAgentSession.attach(GatewayClient(transport))
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
    assert methods == [
        "session.open",
        "subscription.subscribe",
        "subscription.unsubscribe",
    ]


def test_interrupt_cancels_the_active_gateway_turn_and_drains_its_terminal() -> None:
    async def run() -> list[str]:
        transport = _Transport()
        session = await GatewayAgentSession.attach(GatewayClient(transport))
        stream = await session.start_turn("Stop me")
        consuming = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        consuming.cancel()
        await asyncio.gather(consuming, return_exceptions=True)

        await session.interrupt()
        await session.close()
        return [method for method, _ in transport.requests]

    assert asyncio.run(run()) == [
        "session.open",
        "subscription.subscribe",
        "turn.start",
        "turn.cancel",
        "subscription.unsubscribe",
    ]


def test_gateway_turn_failure_is_exposed_to_the_voice_bridge() -> None:
    async def run() -> None:
        transport = _Transport()
        session = await GatewayAgentSession.attach(GatewayClient(transport))
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
