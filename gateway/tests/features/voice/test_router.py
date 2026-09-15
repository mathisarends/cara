from fastapi.testclient import TestClient

_FORMATS = {
    "input_formats": [{"encoding": "pcm_s16le", "sample_rate": 16_000, "channels": 1}],
    "output_formats": [{"encoding": "pcm_s16le", "sample_rate": 24_000, "channels": 1}],
}


def test_open_list_get_and_close_voice_session(client: TestClient) -> None:
    session_id = _conversation_session(client)
    response = client.post(
        "/v1/voice-sessions",
        json={"session_id": session_id, "device_id": "kitchen", **_FORMATS},
    )

    assert response.status_code == 201
    created = response.json()
    assert created["status"] == "open"
    assert created["media_path"].endswith(f"/{created['id']}/media")
    assert created["media_connected"] is False

    listed = client.get(
        "/v1/voice-sessions",
        params={"device_id": "kitchen", "status": "open"},
    ).json()
    assert [item["id"] for item in listed["voice_sessions"]] == [created["id"]]

    snapshot = client.get(f"/v1/voice-sessions/{created['id']}").json()
    assert snapshot["active_turn_id"] is None
    assert snapshot["last_sequence"] == 0
    assert snapshot["turns"] == []

    closed = client.post(f"/v1/voice-sessions/{created['id']}/close").json()
    assert closed["status"] == "closed"
    assert closed["close_reason"] == "client"


def test_only_one_open_voice_session_per_device(client: TestClient) -> None:
    session_id = _conversation_session(client)
    request = {"session_id": session_id, "device_id": "desk", **_FORMATS}
    assert client.post("/v1/voice-sessions", json=request).status_code == 201

    conflict = client.post("/v1/voice-sessions", json=request)

    assert conflict.status_code == 409
    assert conflict.json()["code"] == "voice_session_already_open"


def test_media_socket_owns_the_voice_session(client: TestClient) -> None:
    session_id = _conversation_session(client)
    voice_session = client.post(
        "/v1/voice-sessions",
        json={"session_id": session_id, "device_id": "media", **_FORMATS},
    ).json()

    with client.websocket_connect(voice_session["media_path"]):
        snapshot = client.get(f"/v1/voice-sessions/{voice_session['id']}").json()
        assert snapshot["voice_session"]["media_connected"] is True

    snapshot = client.get(f"/v1/voice-sessions/{voice_session['id']}").json()
    assert snapshot["voice_session"]["media_connected"] is False


def _conversation_session(client: TestClient) -> str:
    response = client.post("/v1/sessions", json={"channel": {"name": "voice"}})
    return response.json()["id"]
