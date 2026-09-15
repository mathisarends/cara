from uuid import uuid4

from fastapi.testclient import TestClient

_ALARMS = "/v1/owners/owner/alarms"
_DAILY = {
    "kind": "weekly",
    "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
    "local_time": "06:00",
    "timezone": "Europe/Berlin",
}


def test_create_list_update_and_delete_an_alarm(client: TestClient) -> None:
    session = _session(client)

    created = client.post(
        _ALARMS,
        json={
            "target": {"kind": "session", "session_id": session},
            "recurrence": _DAILY,
            "routine": {"skill": "wake-up"},
            "pre_wake_minutes": 30,
            "name": "Wecker",
        },
    )
    assert created.status_code == 201
    alarm = created.json()
    assert alarm["recurrence"] == _DAILY
    assert alarm["routine"] == {"skill": "wake-up", "note": None}
    assert alarm["occurrence"]["state"] == "upcoming"
    assert alarm["next_run"]["phase"] == "pre_wake"
    assert client.get(f"{_ALARMS}/{alarm['id']}").json()["id"] == alarm["id"]
    assert [item["id"] for item in client.get(_ALARMS).json()["alarms"]] == [
        alarm["id"]
    ]

    updated = client.put(
        f"{_ALARMS}/{alarm['id']}",
        json={
            "recurrence": {**_DAILY, "days": ["mon", "fri"]},
            "routine": {"skill": "wake-up", "note": "ohne Musik"},
        },
    )
    assert updated.status_code == 200
    assert updated.json()["recurrence"]["days"] == ["mon", "fri"]
    assert updated.json()["pre_wake_minutes"] is None

    disabled = client.put(f"{_ALARMS}/{alarm['id']}/enabled", json={"enabled": False})
    assert disabled.json()["occurrence"] is None
    client.put(f"{_ALARMS}/{alarm['id']}/enabled", json={"enabled": True})
    skipped = client.post(f"{_ALARMS}/{alarm['id']}/skip-next")
    assert skipped.status_code == 200
    assert len(skipped.json()["skipped_dates"]) == 1

    deleted = client.delete(f"{_ALARMS}/{alarm['id']}")
    assert deleted.status_code == 204
    assert client.get(_ALARMS).json() == {"alarms": []}


def test_snoozing_or_dismissing_a_silent_alarm_conflicts(client: TestClient) -> None:
    alarm = _create(client)

    snoozed = client.post(f"{_ALARMS}/{alarm['id']}/snooze", json={"minutes": 9})
    dismissed = client.post(f"{_ALARMS}/{alarm['id']}/dismiss")

    for response in (snoozed, dismissed):
        assert response.status_code == 409
        assert response.json()["code"] == "alarm_state_conflict"


def test_an_alarm_is_hidden_from_other_owners(client: TestClient) -> None:
    alarm = _create(client)

    response = client.get(f"/v1/owners/intruder/alarms/{alarm['id']}")

    assert response.status_code == 404
    assert response.json()["code"] == "alarm_not_found"


def test_creating_an_alarm_for_an_unknown_session_is_not_found(
    client: TestClient,
) -> None:
    response = client.post(
        _ALARMS,
        json={
            "target": {"kind": "session", "session_id": str(uuid4())},
            "recurrence": _DAILY,
            "routine": {"skill": "wake-up"},
        },
    )

    assert response.status_code == 404
    assert response.json()["code"] == "session_not_found"


def test_rejects_invalid_requests(client: TestClient) -> None:
    valid = {
        "target": {"kind": "session", "session_id": _session(client)},
        "recurrence": _DAILY,
        "routine": {"skill": "wake-up"},
    }
    for override in (
        {"recurrence": {**_DAILY, "days": []}},
        {"recurrence": {**_DAILY, "local_time": "25:00"}},
        {"recurrence": {"kind": "once", "wake_at": "2030-01-01T06:00:00"}},
        {"pre_wake_minutes": 0},
        {"pre_wake_minutes": 121},
        {"routine": {"skill": "   "}},
    ):
        response = client.post(_ALARMS, json={**valid, **override})
        assert response.status_code == 422, override

    past = client.post(
        _ALARMS,
        json={
            **valid,
            "recurrence": {"kind": "once", "wake_at": "2000-01-01T06:00:00Z"},
        },
    )
    assert past.status_code == 422
    assert past.json()["code"] == "invalid_alarm"

    alarm = _create(client)
    for minutes in (0, 61):
        response = client.post(
            f"{_ALARMS}/{alarm['id']}/snooze", json={"minutes": minutes}
        )
        assert response.status_code == 422, minutes


def _session(client: TestClient) -> str:
    return client.post("/v1/sessions", json={"channel": {"name": "voice"}}).json()["id"]


def _create(client: TestClient) -> dict:
    return client.post(
        _ALARMS,
        json={
            "target": {"kind": "session", "session_id": _session(client)},
            "recurrence": _DAILY,
            "routine": {"skill": "wake-up"},
        },
    ).json()
