import os
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any, Literal, Self
from uuid import UUID

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from room.features.room.domain import Capability, Device, DeviceKind

DEFAULT_CONFIG_FILE = Path("room.yml")


class RoomConfigError(ValueError):
    """A readable error raised when room configuration cannot be loaded."""


class _ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GatewayConfig(_ConfigModel):
    url: str = "http://127.0.0.1:8000"
    token: str = Field(min_length=1)
    heartbeat_seconds: float = Field(default=15.0, gt=0.0)


class HttpConfig(_ConfigModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8081, ge=1, le=65535)


class PortAudioMicrophoneConfig(_ConfigModel):
    driver: Literal["portaudio"]
    device_id: str = Field(min_length=1)

    def device(self) -> Device:
        return Device(
            self.device_id,
            DeviceKind.MICROPHONE,
            frozenset({Capability.AUDIO_INPUT}),
        )


class SonosSpeakerConfig(_ConfigModel):
    driver: Literal["sonos"]
    device_id: str = Field(min_length=1)
    ip_address: str = Field(min_length=1)

    def device(self) -> Device:
        return Device(
            self.device_id,
            DeviceKind.SPEAKER,
            frozenset({Capability.AUDIO_OUTPUT, Capability.MEDIA_PLAYBACK}),
        )


class HueLightConfig(_ConfigModel):
    driver: Literal["hue"]
    device_id: str = Field(min_length=1)
    room_name: str = Field(min_length=1)

    def device(self) -> Device:
        return Device(
            self.device_id,
            DeviceKind.LIGHT,
            frozenset({Capability.LIGHT}),
        )


DeviceConfig = Annotated[
    PortAudioMicrophoneConfig | SonosSpeakerConfig | HueLightConfig,
    Field(discriminator="driver"),
]


class RoomConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CARA_ROOM_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    room_id: UUID
    gateway: GatewayConfig
    devices: tuple[DeviceConfig, ...]
    http: HttpConfig = Field(default_factory=HttpConfig)

    def build_devices(self) -> tuple[Device, ...]:
        return tuple(config.device() for config in self.devices)

    @classmethod
    def from_yaml(cls, path: str | Path = DEFAULT_CONFIG_FILE) -> Self:
        config_path = Path(path)
        if not config_path.is_file():
            raise RoomConfigError(
                f"Room configuration file was not found: {config_path.resolve()}"
            )
        try:
            document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as error:
            raise RoomConfigError(
                f"Could not read room configuration {config_path.resolve()}: {error}"
            ) from error
        if not isinstance(document, dict):
            raise RoomConfigError(
                "The YAML document must contain a mapping at its root"
            )
        unknown_fields = sorted(set(document) - set(cls.model_fields))
        if unknown_fields:
            rendered = ", ".join(str(field) for field in unknown_fields)
            raise RoomConfigError(
                f"Unknown top-level configuration field(s): {rendered}"
            )
        gateway = document.get("gateway")
        token = os.environ.get("CARA_GATEWAY_TOKEN")
        if token and isinstance(gateway, dict):
            document = {**document, "gateway": {**gateway, "token": token}}
        try:
            return cls.model_validate(document)
        except ValidationError as error:
            details = "\n".join(
                _format_validation_error(item) for item in error.errors()
            )
            raise RoomConfigError(
                f"Invalid room configuration in {config_path.resolve()}:\n{details}"
            ) from error


def _format_validation_error(error: Mapping[str, Any]) -> str:
    location = ".".join(str(part) for part in error["loc"])
    message = str(error["msg"])
    value = error.get("input")
    if any(
        sensitive in location.lower()
        for sensitive in ("key", "password", "secret", "token")
    ):
        value = "<redacted>"
    return f"  - {location}: {message} (received {value!r})"
