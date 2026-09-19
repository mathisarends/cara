from uuid import uuid4

from fastapi.testclient import TestClient

_CHANNEL = {"channel": {"name": "cli"}}


def test_open_reuses_the_latest_session_of_a_channel(client: TestClient) -> None:
    created = client.post("/v1/sessions", json=_CHANNEL)
    opened = client.post("/v1/sessions/open", json=_CHANNEL)

    assert created.status_code == 201
    assert opened.status_code == 200
    assert opened.json() == created.json()


def test_open_keeps_reusing_the_latest_session(client: TestClient) -> None:
    first = client.post("/v1/sessions/open", json=_CHANNEL).json()

    second = client.post("/v1/sessions/open", json=_CHANNEL).json()

    assert second == first


def test_list_sorts_by_creation_time_and_applies_the_limit(
    client: TestClient,
) -> None:
    ids = [client.post("/v1/sessions", json=_CHANNEL).json()["id"] for _ in range(3)]

    newest = client.get("/v1/sessions", params={"limit": 2})
    oldest = client.get("/v1/sessions", params={"limit": 2, "sort": "asc"})

    assert [s["id"] for s in newest.json()["sessions"]] == [ids[2], ids[1]]
    assert [s["id"] for s in oldest.json()["sessions"]] == [ids[0], ids[1]]


def test_list_rejects_a_limit_outside_the_allowed_range(client: TestClient) -> None:
    assert client.get("/v1/sessions", params={"limit": 0}).status_code == 422
    assert client.get("/v1/sessions", params={"limit": 101}).status_code == 422


def test_get_returns_a_session_snapshot(client: TestClient) -> None:
    session = client.post("/v1/sessions", json=_CHANNEL).json()

    response = client.get(f"/v1/sessions/{session['id']}")

    assert response.json() == {"session": session, "items": [], "turn_active": False}


def test_an_unknown_session_is_a_not_found_problem(client: TestClient) -> None:
    response = client.get(f"/v1/sessions/{uuid4()}")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "session_not_found"
