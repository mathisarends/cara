from pathlib import Path

import pytest

from voice import VoiceConfigError, VoiceSessionConfig
from voice.config import AudioOutputType, BargeInType


def test_loads_friendly_yaml_values(tmp_path: Path) -> None:
    config_path = _write(
        tmp_path,
        """
gateway:
  token: test-token
room: kitchen
activation:
  wake_word:
    word: hey_jarvis
barge_in:
  type: speech
audio:
  output:
    type: local
""",
    )

    config = VoiceSessionConfig.from_yaml(config_path)

    assert config.room == "kitchen"
    assert config.activation.wake_word.word == "hey_jarvis"
    assert config.barge_in.type is BargeInType.SPEECH
    assert config.audio.output.type is AudioOutputType.LOCAL


def test_reports_allowed_values_for_invalid_strategy(tmp_path: Path) -> None:
    config_path = _write(
        tmp_path,
        """
gateway:
  token: test-token
barge_in:
  type: shouting
""",
    )

    with pytest.raises(VoiceConfigError) as raised:
        VoiceSessionConfig.from_yaml(config_path)

    message = str(raised.value)
    assert str(config_path.resolve()) in message
    assert "barge_in" in message
    assert "disabled" in message
    assert "wake_word" in message
    assert "speech" in message


def test_reports_malformed_yaml_with_its_path(tmp_path: Path) -> None:
    config_path = _write(tmp_path, "gateway: [\n")

    with pytest.raises(VoiceConfigError) as raised:
        VoiceSessionConfig.from_yaml(config_path)

    message = str(raised.value)
    assert "Could not parse voice configuration" in message
    assert str(config_path.resolve()) in message


def test_rejects_unknown_yaml_fields(tmp_path: Path) -> None:
    config_path = _write(
        tmp_path,
        """
gateway:
  token: test-token
integrations:
  hue:
    enabled: true
    room_nam: Kitchen
""",
    )

    with pytest.raises(VoiceConfigError, match="room_nam"):
        VoiceSessionConfig.from_yaml(config_path)


def test_accepts_legacy_yaml_filename(tmp_path: Path, monkeypatch) -> None:
    legacy_path = tmp_path / "voice.yaml"
    legacy_path.write_text(
        "gateway:\n  token: test-token\nroom: bedroom\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    config = VoiceSessionConfig.from_yaml()

    assert config.room == "bedroom"


def _write(directory: Path, content: str) -> Path:
    path = directory / "voice.yml"
    path.write_text(content, encoding="utf-8")
    return path
