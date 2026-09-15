from uuid import uuid4

from fastapi.testclient import TestClient

_CHANNEL = {"channel": {"name": "cli"}}


def test_open_reuses_the_latest_session_of_a_channel(client: TestClient) -> None:
    created = client.post("/v1/sessions", json=_CHANNEL)
    opened = client.post("/v1/sessions/open", json=_CHANNEL)

    assert created.status_code == 201
    assert opened.status_code == 200
    assert opened.json() == created.json()


def test_get_returns_a_session_snapshot(client: TestClient) -> None:
    session = client.post("/v1/sessions", json=_CHANNEL).json()

    response = client.get(f"/v1/sessions/{session['id']}")

    assert response.json() == {"session": session, "items": [], "turn_active": False}


def test_an_unknown_session_is_a_not_found_problem(client: TestClient) -> None:
    response = client.get(f"/v1/sessions/{uuid4()}")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "session_not_found"


def test_turn_lifecycle_commands_are_bodyless(client: TestClient) -> None:
    session_id = client.post("/v1/sessions", json=_CHANNEL).json()["id"]

    prepared = client.post(f"/v1/sessions/{session_id}/turn/prepare")
    started = client.post(f"/v1/sessions/{session_id}/turn", json={"message": "Hi"})
    finished = client.post(f"/v1/sessions/{session_id}/turn/finish")

    assert (prepared.status_code, prepared.content) == (204, b"")
    assert (started.status_code, started.content) == (202, b"")
    assert (finished.status_code, finished.content) == (204, b"")


def test_cancelling_without_an_active_turn_is_a_conflict(client: TestClient) -> None:
    session_id = client.post("/v1/sessions", json=_CHANNEL).json()["id"]

    response = client.delete(f"/v1/sessions/{session_id}/turn")

    assert response.status_code == 409
    assert response.json()["code"] == "no_active_turn"
