from fastapi.testclient import TestClient


def test_model_options_lists_configured_models_and_reasoning_efforts(
    client: TestClient,
) -> None:
    response = client.get("/v1/llm/model-options")

    assert response.status_code == 200
    payload = response.json()
    assert payload["default_model"] in payload["models"]
    assert "high" in payload["reasoning_efforts"]
