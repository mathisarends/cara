from uuid import uuid4

from fastapi.testclient import TestClient

_AUTOMATIONS = "/v1/owners/owner/automations"


def test_create_list_update_and_delete_an_automation(client: TestClient) -> None:
    session = client.post("/v1/sessions", json={"channel": {"name": "cli"}}).json()
    payload = {"instruction": "Drink water", "created_from_turn_id": str(uuid4())}

    created = client.post(
        _AUTOMATIONS,
        json={
            "target": {"kind": "session", "session_id": session["id"]},
            "schedule": {"kind": "interval", "every_seconds": 1800},
            "payload": payload,
            "name": "Hydration",
        },
    )
    assert created.status_code == 201
    automation = created.json()
    assert automation["owner_id"] == "owner"
    assert automation["payload"] == {"kind": "reminder", **payload}
    assert client.get(_AUTOMATIONS).json() == {"automations": [automation]}
    assert client.get(f"{_AUTOMATIONS}/{automation['id']}").json() == automation

    cron = {"kind": "cron", "expression": "0 9 * * *", "timezone": "Europe/Berlin"}
    updated = client.put(
        f"{_AUTOMATIONS}/{automation['id']}",
        json={"schedule": cron, "payload": payload, "name": "Morning water"},
    )
    assert updated.status_code == 200
    assert updated.json()["schedule"] == cron
    assert updated.json()["name"] == "Morning water"

    deleted = client.delete(f"{_AUTOMATIONS}/{automation['id']}")
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert client.get(_AUTOMATIONS).json() == {"automations": []}


def test_an_automation_is_hidden_from_other_owners(client: TestClient) -> None:
    session = client.post("/v1/sessions", json={"channel": {"name": "cli"}}).json()
    automation = client.post(
        _AUTOMATIONS,
        json={
            "target": {"kind": "session", "session_id": session["id"]},
            "schedule": {"kind": "interval", "every_seconds": 60},
            "payload": {"instruction": "Stretch", "created_from_turn_id": str(uuid4())},
        },
    ).json()

    response = client.get(f"/v1/owners/intruder/automations/{automation['id']}")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "automation_not_found"


def test_creating_an_automation_for_an_unknown_session_is_not_found(
    client: TestClient,
) -> None:
    response = client.post(
        _AUTOMATIONS,
        json={
            "target": {"kind": "session", "session_id": str(uuid4())},
            "schedule": {"kind": "interval", "every_seconds": 60},
            "payload": {"instruction": "Stretch", "created_from_turn_id": str(uuid4())},
        },
    )

    assert response.status_code == 404
    assert response.json()["code"] == "session_not_found"


def test_rejects_invalid_requests(client: TestClient) -> None:
    session = client.post("/v1/sessions", json={"channel": {"name": "cli"}}).json()
    valid = {
        "target": {"kind": "session", "session_id": session["id"]},
        "schedule": {"kind": "interval", "every_seconds": 60},
        "payload": {"instruction": "Stretch", "created_from_turn_id": str(uuid4())},
    }
    for override in (
        {"schedule": {"kind": "cron", "expression": "0 9 * * *", "timezone": "Mars"}},
        {"schedule": {"kind": "cron", "expression": "0 9 *", "timezone": "UTC"}},
        {"schedule": {"kind": "at", "run_at": "2030-01-01T09:00:00"}},
        {"schedule": {"kind": "interval", "every_seconds": 0}},
        {"payload": {**valid["payload"], "instruction": "   "}},
    ):
        response = client.post(_AUTOMATIONS, json={**valid, **override})
        assert response.status_code == 422, override
