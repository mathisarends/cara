from uuid import UUID, uuid4

from fastapi.testclient import TestClient

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
