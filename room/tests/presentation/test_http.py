from fastapi.testclient import TestClient

from room.app import create_app
from room.platform import RoomConfig


def test_app_exposes_health_and_unavailable_readiness() -> None:
    config = RoomConfig.model_validate(
        {
            "room_id": "8edc5cf8-0caa-4d5a-9b5b-10da42dfdde2",
            "gateway": {
                "url": "http://127.0.0.1:1",
                "token": "test-token",
                "heartbeat_seconds": 0.01,
            },
            "devices": [],
        }
    )
    app = create_app(config)

    with TestClient(app) as client:
        health = client.get("/health")
        unavailable = client.get("/ready")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert unavailable.status_code == 503
    assert unavailable.json()["code"] == "room_not_ready"
    assert unavailable.json()["detail"] == (
        "Room is not ready: gateway_registered, gateway_connected, voice_ready"
    )
