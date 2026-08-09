import asyncio
import json
import sqlite3
from unittest.mock import patch
from uuid import UUID, uuid4

from dishka import Provider, Scope, provide
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway import create_app
from gateway.container import create_container
from gateway.features.conversation.application import AgentEventBus, AgentRunner
from gateway.features.conversation.domain import (
    ChatCompleted,
    ChatDelta,
    ToolCallCompleted,
    ToolCallStarted,
)
from gateway.infrastructure import DatabaseSettings

_TEST_DATABASE_SETTINGS = DatabaseSettings(database_url="sqlite+aiosqlite:///:memory:")


class StaticAgentRunner(AgentRunner):
    async def run(
        self,
        session_id: UUID,
        metadata: dict[str, object],
        event_bus: AgentEventBus,
    ) -> None:
        del session_id, metadata
        await event_bus.dispatch(ChatDelta(text="Hallo"))
        await event_bus.dispatch(ChatCompleted(text="Hallo"))


class _TestAgentProvider(Provider):
    scope = Scope.APP

    def __init__(self, agent: AgentRunner) -> None:
        self._agent = agent
        super().__init__()

    @provide
    def agent(self) -> AgentRunner:
        return self._agent


def _create_app(
    agent: AgentRunner | None = None,
    database_settings: DatabaseSettings = _TEST_DATABASE_SETTINGS,
) -> FastAPI:
    with (
        patch(
            "gateway.container._AgentProvider",
            return_value=_TestAgentProvider(agent or StaticAgentRunner()),
        ),
        patch(
            "gateway.infrastructure.database.di.DatabaseSettings",
            return_value=database_settings,
        ),
    ):
        container = create_container()
    with patch("gateway.main.create_container", return_value=container):
        return create_app()


class ToolAgentRunner(AgentRunner):
    async def run(
        self,
        session_id: UUID,
        metadata: dict[str, object],
        event_bus: AgentEventBus,
    ) -> None:
        del session_id, metadata
        await event_bus.dispatch(
            ToolCallStarted(
                call_id="call_1",
                name="lights.turn_on",
                arguments={"room": "office"},
                metadata={"provider": "hue"},
            )
        )
        await event_bus.dispatch(
            ToolCallCompleted(
                call_id="call_1",
                name="lights.turn_on",
                result={"on": True},
            )
        )
        await event_bus.dispatch(ChatCompleted(text="Erledigt"))


class BlockingAgentRunner(AgentRunner):
    async def run(
        self,
        session_id: UUID,
        metadata: dict[str, object],
        event_bus: AgentEventBus,
    ) -> None:
        del session_id, metadata
        await event_bus.dispatch(ChatDelta(text="gestartet"))
        await asyncio.Event().wait()


def test_health() -> None:
    with TestClient(_create_app()) as client:
        response = client.get("/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness() -> None:
    with TestClient(_create_app()) as client:
        response = client.get("/v1/readiness")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_session_rest_lifecycle() -> None:
    with TestClient(_create_app()) as client:
        created = client.post(
            "/v1/sessions", json={"metadata": {"channel": "terminal"}}
        )
        fetched = client.get(f"/v1/sessions/{created.json()['id']}")

    assert created.status_code == 201
    assert UUID(created.json()["id"])
    assert fetched.json() == created.json()


def test_session_not_found_uses_feature_exception_mapping() -> None:
    missing_id = uuid4()
    with TestClient(_create_app()) as client:
        response = client.get(f"/v1/sessions/{missing_id}")

    assert response.status_code == 404
    assert response.json() == {"detail": f"Session {missing_id} not found"}


def test_session_is_persisted_between_app_instances(tmp_path) -> None:
    database_path = (tmp_path / "gateway.sqlite3").as_posix()
    settings = DatabaseSettings(database_url=f"sqlite+aiosqlite:///{database_path}")

    with TestClient(_create_app(database_settings=settings)) as client:
        created = client.post("/v1/sessions", json={}).json()

    with TestClient(_create_app(database_settings=settings)) as client:
        fetched = client.get(f"/v1/sessions/{created['id']}")

    assert fetched.status_code == 200
    assert fetched.json() == created


def test_openapi_has_stable_operation_ids_and_response_models() -> None:
    with TestClient(_create_app()) as client:
        schema = client.get("/openapi.json").json()

    paths = schema["paths"]
    assert paths["/v1/health"]["get"]["operationId"] == "get_gateway_health"
    assert paths["/v1/readiness"]["get"]["operationId"] == "get_gateway_readiness"
    assert paths["/v1/sessions"]["post"]["operationId"] == "create_session"
    assert paths["/v1/sessions/{session_id}"]["get"]["operationId"] == "get_session"
    assert (
        paths["/v1/sessions"]["post"]["responses"]["201"]["content"][
            "application/json"
        ]["schema"]["$ref"]
        == "#/components/schemas/SessionResponse"
    )
    assert (
        paths["/v1/sessions/{session_id}"]["get"]["responses"]["404"]["content"][
            "application/json"
        ]["schema"]["$ref"]
        == "#/components/schemas/ErrorResponse"
    )
    event_message = schema["components"]["schemas"]["GatewayEventMessage"]
    assert event_message["discriminator"]["propertyName"] == "type"
    assert "ChatDeltaPayload" in schema["components"]["schemas"]


def test_chat_streams_agent_events() -> None:
    with TestClient(_create_app()) as client:
        session_id = client.post("/v1/sessions", json={}).json()["id"]
        with client.websocket_connect(f"/v1/sessions/{session_id}/events") as socket:
            response = client.post(
                f"/v1/sessions/{session_id}/chat",
                json={"text": "Hallo"},
            )
            events = []
            while not events or events[-1]["type"] != "chat.completed":
                events.append(socket.receive_json())

    assert response.status_code == 202
    assert all(event["type"] == "chat.delta" for event in events[:-1])
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
    assert (
        "".join(event["data"]["text"] for event in events[:-1])
        == events[-1]["data"]["text"]
    )


def test_session_event_stream_supports_multiple_clients() -> None:
    with TestClient(_create_app()) as client:
        session_id = client.post("/v1/sessions", json={}).json()["id"]
        with (
            client.websocket_connect(f"/v1/sessions/{session_id}/events") as first,
            client.websocket_connect(f"/v1/sessions/{session_id}/events") as second,
        ):
            response = client.post(
                f"/v1/sessions/{session_id}/chat",
                json={"text": "shared"},
            )
            first_turn_event = first.receive_json()
            second_turn_event = second.receive_json()

    assert response.status_code == 202
    assert second_turn_event == first_turn_event


def test_invalid_chat_request_is_rejected() -> None:
    with TestClient(_create_app()) as client:
        session_id = client.post("/v1/sessions", json={}).json()["id"]
        response = client.post(
            f"/v1/sessions/{session_id}/chat",
            json={"text": ""},
        )

    assert response.status_code == 422


def test_tool_calls_keep_call_id_and_metadata() -> None:
    with TestClient(_create_app(ToolAgentRunner())) as client:
        session_id = client.post("/v1/sessions", json={}).json()["id"]
        with client.websocket_connect(f"/v1/sessions/{session_id}/events") as socket:
            response = client.post(
                f"/v1/sessions/{session_id}/chat",
                json={"text": "Licht an"},
            )
            events = [socket.receive_json() for _ in range(3)]

    assert response.status_code == 202
    started, completed = events[:2]
    assert started["type"] == "tool_call.started"
    assert started["call_id"] == "call_1"
    assert started["metadata"] == {"provider": "hue"}
    assert started["data"] == {
        "name": "lights.turn_on",
        "arguments": {"room": "office"},
    }
    assert completed["type"] == "tool_call.completed"
    assert completed["call_id"] == "call_1"
    assert completed["data"]["result"] == {"on": True}


def test_complete_chat_history_is_persisted(tmp_path) -> None:
    database_path = (tmp_path / "gateway.sqlite3").as_posix()
    settings = DatabaseSettings(database_url=f"sqlite+aiosqlite:///{database_path}")

    with (
        TestClient(_create_app(ToolAgentRunner(), settings)) as client,
    ):
        session_id = client.post("/v1/sessions", json={}).json()["id"]
        with client.websocket_connect(f"/v1/sessions/{session_id}/events") as socket:
            client.post(
                f"/v1/sessions/{session_id}/chat",
                json={"text": "Licht an"},
            )
            events = [socket.receive_json() for _ in range(3)]
            assert events[-1]["type"] == "chat.completed"

    with sqlite3.connect(database_path) as database:
        runs_table = database.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name = 'gateway_runs'"
        ).fetchone()
        user_message = database.execute(
            "SELECT position, content FROM gateway_session_user_messages"
        ).fetchone()
        assistant_message = database.execute(
            "SELECT position, content FROM gateway_session_assistant_messages"
        ).fetchone()
        sequence = database.execute(
            "SELECT position FROM gateway_session_tool_call_sequences"
        ).fetchone()
        tool_call = database.execute(
            """
            SELECT position, call_id, function_name, function_arguments, state, result
            FROM gateway_session_tool_calls
            """
        ).fetchone()

    assert runs_table is None
    assert user_message == (0, "Licht an")
    assert sequence == (1,)
    assert assistant_message == (2, "Erledigt")
    assert tool_call[:3] == (0, "call_1", "lights.turn_on")
    assert json.loads(tool_call[3]) == {"room": "office"}
    assert tool_call[4] == "completed"
    assert json.loads(tool_call[5]) == {"on": True}


def test_session_rejects_a_second_active_turn() -> None:
    with TestClient(_create_app(BlockingAgentRunner())) as client:
        session_id = client.post("/v1/sessions", json={}).json()["id"]
        with client.websocket_connect(f"/v1/sessions/{session_id}/events") as socket:
            first = client.post(
                f"/v1/sessions/{session_id}/chat",
                json={"text": "First"},
            )
            assert socket.receive_json()["type"] == "chat.delta"
            second = client.post(
                f"/v1/sessions/{session_id}/chat",
                json={"text": "Second"},
            )

    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json() == {
        "detail": f"Session {session_id} already has an active turn"
    }
