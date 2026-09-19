import asyncio
from pathlib import Path

import pytest
from doubles import (
    FakeAudioDevices,
    FakeVoiceBackend,
    FakeVoiceBackendConnector,
    settle,
)

from voice import VoiceSession, VoiceSessionFactory
from voice.audio import AudioFormat
from voice.backend import SessionClosed

_CONFIG = """
gateway:
  token: test-token
room: office
activation:
  wake_word:
    enabled: false
barge_in:
  type: disabled
audio:
  echo_cancellation:
    enabled: false
integrations:
  sounds:
    enabled: false
"""


def test_from_yaml_composes_a_session_on_the_injected_ports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "voice.yml").write_text(_CONFIG, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    backend = FakeVoiceBackend()
    connector = FakeVoiceBackendConnector(backend)
    devices = FakeAudioDevices()

    async def scenario() -> None:
        session = await VoiceSessionFactory.from_yaml(
            backend_connector=connector, audio_devices=devices
        )
        assert isinstance(session, VoiceSession)

        run = asyncio.create_task(session.run())
        await settle()
        backend.emit(SessionClosed(reason="done"))
        await asyncio.wait_for(run, timeout=1)

    asyncio.run(scenario())

    assert connector.options is not None
    assert connector.options.room == "office"
    assert connector.options.input_format == AudioFormat(sample_rate=16_000)
    assert backend.close_calls == 1
    assert devices.input.stop_calls == 1
    assert devices.output.stop_calls == 1


def test_a_failed_composition_closes_what_was_opened(tmp_path: Path) -> None:
    config_path = tmp_path / "voice.yml"
    config_path.write_text(_CONFIG, encoding="utf-8")

    class _MismatchedBackend(FakeVoiceBackend):
        @property
        def input_format(self) -> AudioFormat:
            return AudioFormat(sample_rate=48_000)

    backend = _MismatchedBackend()

    async def scenario() -> None:
        with pytest.raises(ValueError, match="sample rate"):
            await VoiceSessionFactory.from_yaml(
                config_path,
                backend_connector=FakeVoiceBackendConnector(backend),
                audio_devices=FakeAudioDevices(),
            )

    asyncio.run(scenario())

    assert backend.close_calls == 1
