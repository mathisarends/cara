from pathlib import Path

from room.features.room.domain import Capability, DeviceKind
from room.platform import RoomConfig


def test_loads_devices_and_derives_capabilities(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "room.yml"
    config_path.write_text(
        """
room_id: 8edc5cf8-0caa-4d5a-9b5b-10da42dfdde2
gateway:
  url: http://gateway:8000
  token: yaml-token
devices:
  - device_id: microphone
    driver: portaudio
  - device_id: speaker
    driver: sonos
    ip_address: 192.168.1.20
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("CARA_GATEWAY_TOKEN", "environment-token")

    config = RoomConfig.from_yaml(config_path)
    microphone, speaker = config.build_devices()

    assert config.gateway.token == "environment-token"
    assert microphone.kind is DeviceKind.MICROPHONE
    assert microphone.capabilities == frozenset({Capability.AUDIO_INPUT})
    assert speaker.kind is DeviceKind.SPEAKER
    assert speaker.capabilities == frozenset(
        {Capability.AUDIO_OUTPUT, Capability.MEDIA_PLAYBACK}
    )
