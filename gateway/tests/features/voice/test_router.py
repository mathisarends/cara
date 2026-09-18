from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from gateway.features.voice.presentation.media import (
    InMemoryMediaSessions,
    MediaFrame,
    MediaFrameKind,
)

_FORMATS = {
    "input_formats": [{"encoding": "pcm_s16le", "sample_rate": 16_000, "channels": 1}],
    "output_formats": [{"encoding": "pcm_s16le", "sample_rate": 24_000, "channels": 1}],
}


def test_open_list_get_and_close_voice_session(client: TestClient) -> None:
    session_id = _conversation_session(client)
    response = client.post(
        "/v1/voice-sessions",
        json={"session_id": session_id, "room": "kitchen", **_FORMATS},
    )

    assert response.status_code == 201
    created = response.json()
    assert created["status"] == "open"
    assert created["media_path"].endswith(f"/{created['id']}/media")
    assert created["media_connected"] is False

    listed = client.get(
        "/v1/voice-sessions",
        params={"room": "kitchen", "status": "open"},
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
    request = {"session_id": session_id, "room": "desk", **_FORMATS}
    assert client.post("/v1/voice-sessions", json=request).status_code == 201

    conflict = client.post("/v1/voice-sessions", json=request)

    assert conflict.status_code == 409
    assert conflict.json()["code"] == "voice_session_already_open"


def test_media_socket_is_bidirectional_and_owns_the_voice_session(
    client: TestClient,
) -> None:
    session_id = _conversation_session(client)
    voice_session = client.post(
        "/v1/voice-sessions",
        json={"session_id": session_id, "room": "media", **_FORMATS},
    ).json()

    with client.websocket_connect(voice_session["media_path"]) as socket:
        snapshot = client.get(f"/v1/voice-sessions/{voice_session['id']}").json()
        assert snapshot["voice_session"]["media_connected"] is True

        client.portal.call(_send_output_frame, client.app, UUID(voice_session["id"]))
        frame = MediaFrame.decode(socket.receive_bytes())
        assert frame.kind is MediaFrameKind.OUTPUT_PCM
        assert frame.payload == b"audio"

        socket.send_text('{"type":"end"}')
        with pytest.raises(WebSocketDisconnect):
            socket.receive_bytes()

    snapshot = client.get(f"/v1/voice-sessions/{voice_session['id']}").json()
    assert snapshot["voice_session"]["media_connected"] is False


async def _send_output_frame(app: FastAPI, voice_session_id: UUID) -> None:
    media = await app.state.dishka_container.get(InMemoryMediaSessions)
    await media.send_audio(
        voice_session_id,
        voice_turn_index=1,
        sequence=2,
        timestamp_ms=3,
        payload=b"audio",
    )


def _conversation_session(client: TestClient) -> str:
    response = client.post("/v1/sessions", json={"channel": {"name": "voice"}})
    return response.json()["id"]
