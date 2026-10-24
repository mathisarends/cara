from contextlib import ExitStack
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketDenialResponse

_ROOM_ID = UUID("8edc5cf8-0caa-4d5a-9b5b-10da42dfdde2")


def test_registration_and_connection_presence(client: TestClient) -> None:
    registration = {
        "client_version": "1.0.0",
        "devices": [
            {
                "device_id": "microphone",
                "kind": "microphone",
                "capabilities": ["audio_input"],
            },
            {
                "device_id": "speaker",
                "kind": "speaker",
                "capabilities": ["audio_output", "media_playback"],
            },
        ],
    }
    response = client.put(f"/v1/rooms/{_ROOM_ID}/registration", json=registration)

    assert response.status_code == 200
    assert response.json()["online"] is False

    with client.websocket_connect(f"/v1/rooms/{_ROOM_ID}/channel") as socket:
        connected = client.get(f"/v1/rooms/{_ROOM_ID}")
        assert connected.json()["online"] is True
        assert set(connected.json()["functions"]) == {
            "conversation",
            "announce",
            "music",
        }

        socket.send_json(
            {
                "jsonrpc": "2.0",
                "id": "state-1",
                "method": "room.report_state",
                "params": {"state": "listening"},
            }
        )
        assert socket.receive_json()["result"] == {"accepted": True}
        assert client.get(f"/v1/rooms/{_ROOM_ID}").json()["state"] == "listening"

    disconnected = client.get(f"/v1/rooms/{_ROOM_ID}")
    assert disconnected.json()["online"] is False
    assert disconnected.json()["state"] == "idle"


def test_unknown_room_registration_is_a_domain_404(client: TestClient) -> None:
    response = client.put(
        f"/v1/rooms/{uuid4()}/registration",
        json={"client_version": "1.0.0", "devices": []},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "room_not_found"


def test_unknown_room_socket_is_rejected_before_acceptance(client: TestClient) -> None:
    with (
        pytest.raises(WebSocketDenialResponse) as denial,
        client.websocket_connect(f"/v1/rooms/{uuid4()}/channel"),
    ):
        pass

    assert denial.value.status_code == 404


def test_unknown_device_report_returns_its_declared_error(client: TestClient) -> None:
    response = client.put(
        f"/v1/rooms/{_ROOM_ID}/registration",
        json={"client_version": "1.0.0", "devices": []},
    )
    assert response.status_code == 200

    with client.websocket_connect(f"/v1/rooms/{_ROOM_ID}/channel") as socket:
        socket.send_json(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "room.report_device",
                "params": {"deviceId": "missing-speaker", "status": "available"},
            }
        )
        failure = socket.receive_json()["error"]

    assert failure["code"] == -32017
    assert failure["data"]["code"] == "room_device_not_found"


def test_room_must_register_before_connecting(client: TestClient) -> None:
    with (
        pytest.raises(WebSocketDenialResponse) as denial,
        client.websocket_connect(f"/v1/rooms/{_ROOM_ID}/channel"),
    ):
        pass

    assert denial.value.status_code == 403
    assert client.get(f"/v1/rooms/{_ROOM_ID}").json()["online"] is False


def test_stale_disconnect_does_not_clear_current_room_presence(
    client: TestClient,
) -> None:
    response = client.put(
        f"/v1/rooms/{_ROOM_ID}/registration",
        json={"client_version": "1.0.0", "devices": []},
    )
    assert response.status_code == 200

    report = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "room.report_state",
        "params": {"state": "idle"},
    }
    with ExitStack() as previous_connection:
        previous_socket_context = client.websocket_connect(
            f"/v1/rooms/{_ROOM_ID}/channel"
        )
        previous_socket = previous_connection.enter_context(previous_socket_context)
        previous_socket.send_json(report)
        assert previous_socket.receive_json()["result"] == {"accepted": True}
        with client.websocket_connect(
            f"/v1/rooms/{_ROOM_ID}/channel"
        ) as current_socket:
            current_socket.send_json(report)
            assert current_socket.receive_json()["result"] == {"accepted": True}
            previous_connection.close()
            assert client.get(f"/v1/rooms/{_ROOM_ID}").json()["online"] is True

    assert client.get(f"/v1/rooms/{_ROOM_ID}").json()["online"] is False
