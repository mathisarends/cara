from pathlib import Path

import pytest
from pydantic import ValidationError

from gateway.agent_plugins import GatewaySettings


def test_settings_load_the_agent_section_from_toml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "gateway.toml").write_text(
        '[agent]\nplugin = "custom"\n[agent.config]\nmodel = "test"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    settings = GatewaySettings(_env_file=None)

    assert settings.agent.plugin == "custom"
    assert settings.agent.config == {"model": "test"}


def test_environment_overrides_the_toml_agent_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "gateway.toml").write_text(
        '[agent]\nplugin = "file-plugin"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CARA_AGENT_PLUGIN", "env-plugin")
    monkeypatch.setenv("CARA_AGENT_CONFIG", '{"answer": 42}')

    settings = GatewaySettings(_env_file=None)

    assert settings.agent.plugin == "env-plugin"
    assert settings.agent.config == {"answer": 42}


def test_settings_load_the_agent_section_from_yaml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "gateway.yaml").write_text(
        """agent:
  plugin: cara
  config:
    models:
      - gpt-5.3-codex-spark
      - gpt-5.6-sol
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    settings = GatewaySettings(_env_file=None)

    assert settings.agent.plugin == "cara"
    assert settings.agent.config == {
        "models": ["gpt-5.3-codex-spark", "gpt-5.6-sol"],
    }


def test_unknown_agent_configuration_fields_are_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "gateway.toml").write_text(
        '[agent]\nplugin = "custom"\nunknown = true\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValidationError, match="unknown"):
        GatewaySettings(_env_file=None)
