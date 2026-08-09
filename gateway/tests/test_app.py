import asyncio
import json
import sqlite3
from collections.abc import AsyncIterator
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway import create_app
from gateway.container import create_container
from gateway.features.conversation.application import AgentRunner
from gateway.features.conversation.domain import (
    AgentOutput,
    ChatCompleted,
    ChatDelta,
    Session,
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
    async def stream(
        self,
        session: Session,
        text: str,
        metadata: dict[str, object],
    ) -> AsyncIterator[AgentOutput]:
        del session, text, metadata
        yield ToolCallStarted(
            call_id="call_1",
            name="lights.turn_on",
            arguments={"room": "office"},
            metadata={"provider": "hue"},
        )
        yield ToolCallCompleted(
            call_id="call_1",
            name="lights.turn_on",
            result={"on": True},
        )
        yield ChatCompleted(text="Erledigt")


class BlockingAgentRunner(AgentRunner):
    async def stream(
        self,
        session: Session,
        text: str,
        metadata: dict[str, object],
    ) -> AsyncIterator[AgentOutput]:
        del session, text, metadata
        yield ChatDelta(text="gestartet")
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
        "run.started",
        "chat.delta",
        "chat.completed",
        "run.completed",
    ]
    run_events = events[1:]
    assert [event["sequence"] for event in run_events] == [1, 2, 3, 4]
    assert {event["run_id"] for event in events} == {events[0]["run_id"]}
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
            first_run_event = first.receive_json()
            second_run_event = second.receive_json()

    assert first_run_event["type"] == "run.started"
    assert second_run_event["event_id"] == first_run_event["event_id"]


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


def test_missing_run_uses_websocket_exception_mapping() -> None:
    with (
        TestClient(_create_app()) as client,
        client.websocket_connect("/v1/ws/web-1") as socket,
    ):
        socket.send_json({"type": "session.create", "request_id": "create"})
        socket.receive_json()
        session_id = socket.receive_json()["session_id"]
        socket.send_json(
            {
                "type": "run.cancel",
                "request_id": "cancel",
                "session_id": session_id,
                "payload": {"run_id": str(uuid4())},
            }
        )
        rejected = socket.receive_json()

    assert rejected["type"] == "command.rejected"
    assert rejected["data"] == {
        "code": "run_not_found",
        "message": "Run not found in this session",
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
        assert events[-1]["type"] == "run.completed"

    with sqlite3.connect(database_path) as database:
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

    assert user_message == (0, "Licht an")
    assert sequence == (1,)
    assert assistant_message == (2, "Erledigt")
    assert tool_call[:3] == (0, "call_1", "lights.turn_on")
    assert json.loads(tool_call[3]) == {"room": "office"}
    assert tool_call[4] == "completed"
    assert json.loads(tool_call[5]) == {"on": True}


def test_run_can_be_cancelled() -> None:
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
        accepted = socket.receive_json()
        socket.receive_json()
        socket.receive_json()

        socket.send_json(
            {
                "type": "run.cancel",
                "request_id": "cancel",
                "session_id": session_id,
                "payload": {"run_id": accepted["run_id"]},
            }
        )
        cancel_accepted = socket.receive_json()
        cancelled = socket.receive_json()

    assert cancel_accepted["type"] == "command.accepted"
    assert cancel_accepted["request_id"] == "cancel"
    assert cancelled["type"] == "run.cancelled"
    assert cancelled["run_id"] == accepted["run_id"]
