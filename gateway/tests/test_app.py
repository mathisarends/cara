import asyncio
import json
import sqlite3
from unittest.mock import patch
from uuid import UUID, uuid4

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


def _create_app(
    agent: AgentRunner | None = None,
    database_settings: DatabaseSettings = _TEST_DATABASE_SETTINGS,
) -> FastAPI:
    container = create_container(agent, database_settings)
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


def test_chat_command_streams_minimal_event_lifecycle() -> None:
    with (
        TestClient(_create_app()) as client,
        client.websocket_connect("/v1/ws/terminal-1") as socket,
    ):
        socket.send_json(
            {
                "type": "session.create",
                "request_id": "req-create",
                "payload": {"metadata": {"channel": "terminal"}},
            }
        )
        accepted = socket.receive_json()
        created = socket.receive_json()
        session_id = created["session_id"]

        socket.send_json(
            {
                "type": "chat.send",
                "request_id": "req-chat",
                "session_id": session_id,
                "payload": {"text": "Hallo"},
            }
        )
        events = [socket.receive_json() for _ in range(5)]

    assert accepted["type"] == "command.accepted"
    assert created["type"] == "session.created"
    assert [event["type"] for event in events] == [
        "command.accepted",
        "turn.started",
        "chat.delta",
        "chat.completed",
        "turn.completed",
    ]
    turn_events = events[1:]
    assert [event["sequence"] for event in turn_events] == [1, 2, 3, 4]
    assert all("run_id" not in event for event in events)
    assert events[2]["data"] == {"text": "Hallo"}


def test_session_get_subscribes_a_second_client() -> None:
    with TestClient(_create_app()) as client:
        session_id = client.post("/v1/sessions", json={}).json()["id"]
        with (
            client.websocket_connect("/v1/ws/web-1") as first,
            client.websocket_connect("/v1/ws/terminal-1") as second,
        ):
            for socket, request_id in ((first, "req-1"), (second, "req-2")):
                socket.send_json(
                    {
                        "type": "session.get",
                        "request_id": request_id,
                        "session_id": session_id,
                    }
                )
                assert socket.receive_json()["type"] == "command.accepted"
                assert socket.receive_json()["type"] == "session.snapshot"

            first.send_json(
                {
                    "type": "chat.send",
                    "request_id": "req-chat",
                    "session_id": session_id,
                    "payload": {"text": "shared"},
                }
            )
            assert first.receive_json()["type"] == "command.accepted"
            first_turn_event = first.receive_json()
            second_turn_event = second.receive_json()

    assert first_turn_event["type"] == "turn.started"
    assert second_turn_event["event_id"] == first_turn_event["event_id"]


def test_invalid_command_is_rejected_without_closing_socket() -> None:
    with (
        TestClient(_create_app()) as client,
        client.websocket_connect("/v1/ws/web-1") as socket,
    ):
        socket.send_json({"type": "chat.send", "request_id": "req-invalid"})
        rejected = socket.receive_json()

        socket.send_json(
            {"type": "session.create", "request_id": "req-next", "payload": {}}
        )
        accepted = socket.receive_json()

    assert rejected["type"] == "command.rejected"
    assert rejected["data"]["code"] == "invalid_command"
    assert accepted["type"] == "command.accepted"


def test_missing_active_turn_uses_websocket_exception_mapping() -> None:
    with (
        TestClient(_create_app()) as client,
        client.websocket_connect("/v1/ws/web-1") as socket,
    ):
        socket.send_json({"type": "session.create", "request_id": "create"})
        socket.receive_json()
        session_id = socket.receive_json()["session_id"]
        socket.send_json(
            {
                "type": "chat.cancel",
                "request_id": "cancel",
                "session_id": session_id,
            }
        )
        rejected = socket.receive_json()

    assert rejected["type"] == "command.rejected"
    assert rejected["data"] == {
        "code": "no_active_turn",
        "message": "Session has no active turn",
    }


def test_tool_calls_keep_call_id_and_metadata() -> None:
    with (
        TestClient(_create_app(ToolAgentRunner())) as client,
        client.websocket_connect("/v1/ws/web-1") as socket,
    ):
        socket.send_json({"type": "session.create", "request_id": "create"})
        socket.receive_json()
        session_id = socket.receive_json()["session_id"]
        socket.send_json(
            {
                "type": "chat.send",
                "request_id": "chat",
                "session_id": session_id,
                "payload": {"text": "Licht an"},
            }
        )
        events = [socket.receive_json() for _ in range(6)]

    started, completed = events[2:4]
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
        client.websocket_connect("/v1/ws/web-1") as socket,
    ):
        socket.send_json({"type": "session.create", "request_id": "create"})
        socket.receive_json()
        session_id = socket.receive_json()["session_id"]
        socket.send_json(
            {
                "type": "chat.send",
                "request_id": "chat",
                "session_id": session_id,
                "payload": {"text": "Licht an"},
            }
        )
        events = [socket.receive_json() for _ in range(6)]
        assert events[-1]["type"] == "turn.completed"

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


def test_active_turn_can_be_cancelled() -> None:
    with (
        TestClient(_create_app(BlockingAgentRunner())) as client,
        client.websocket_connect("/v1/ws/web-1") as socket,
    ):
        socket.send_json({"type": "session.create", "request_id": "create"})
        socket.receive_json()
        session_id = socket.receive_json()["session_id"]
        socket.send_json(
            {
                "type": "chat.send",
                "request_id": "chat",
                "session_id": session_id,
                "payload": {"text": "Arbeite lange"},
            }
        )
        socket.receive_json()
        socket.receive_json()
        socket.receive_json()

        socket.send_json(
            {
                "type": "chat.cancel",
                "request_id": "cancel",
                "session_id": session_id,
            }
        )
        cancel_accepted = socket.receive_json()
        cancelled = socket.receive_json()

    assert cancel_accepted["type"] == "command.accepted"
    assert cancel_accepted["request_id"] == "cancel"
    assert cancelled["type"] == "turn.cancelled"
    assert "run_id" not in cancelled


def test_session_rejects_a_second_active_turn() -> None:
    with (
        TestClient(_create_app(BlockingAgentRunner())) as client,
        client.websocket_connect("/v1/ws/web-1") as socket,
    ):
        socket.send_json({"type": "session.create", "request_id": "create"})
        socket.receive_json()
        session_id = socket.receive_json()["session_id"]
        socket.send_json(
            {
                "type": "chat.send",
                "request_id": "first",
                "session_id": session_id,
                "payload": {"text": "First"},
            }
        )
        socket.receive_json()
        socket.receive_json()
        socket.receive_json()

        socket.send_json(
            {
                "type": "chat.send",
                "request_id": "second",
                "session_id": session_id,
                "payload": {"text": "Second"},
            }
        )
        rejected = socket.receive_json()

    assert rejected["type"] == "command.rejected"
    assert rejected["data"] == {
        "code": "session_busy",
        "message": "Session already has an active turn",
    }
