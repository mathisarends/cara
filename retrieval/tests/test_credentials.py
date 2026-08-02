from pathlib import Path

from retrieval.openai import OpenAICredentials


def test_credentials_load_api_key_from_dotenv(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".env").write_text("OPENAI_API_KEY=test-key\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    credentials = OpenAICredentials()

    assert credentials.api_key.get_secret_value() == "test-key"
