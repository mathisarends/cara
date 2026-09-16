from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal, Self, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    SettingsError,
    YamlConfigSettingsSource,
)

DEFAULT_CONFIG_FILE = Path("voice.yml")
_LEGACY_CONFIG_FILE = Path("voice.yaml")


class VoiceConfigError(ValueError):
    """A readable error raised when the voice YAML cannot be loaded."""


class _ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GatewayConfig(_ConfigModel):
    # The token should normally come from CARA_GATEWAY_TOKEN in .env.
    # Ignore the Gateway server's other CARA_GATEWAY_* variables from .env.
    model_config = ConfigDict(extra="ignore", frozen=True)

    url: str = "http://127.0.0.1:8000"
    token: str = Field(min_length=1)


class SessionConfig(_ConfigModel):
    channel: str = Field(default="voice", min_length=1)
    client_id: str = Field(default="default-voice-client", min_length=1)
    new_session: bool = False
    inactivity_timeout_seconds: float = Field(default=1800, gt=0)


class WakeWordName(StrEnum):
    ALEXA = "alexa"
    HEY_JARVIS = "hey_jarvis"
    HEY_MARVIN = "hey_marvin"
    HEY_MYCROFT = "hey_mycroft"


class WakeWordConfig(_ConfigModel):
    enabled: bool = True
    word: WakeWordName = WakeWordName.HEY_MYCROFT
    sensitivity: float = Field(default=0.5, ge=0.0, le=1.0)
    cooldown_seconds: float = Field(default=1.5, ge=0.0)
    strip_from_command: bool = True


class ActivationConfig(_ConfigModel):
    wake_word: WakeWordConfig = Field(default_factory=WakeWordConfig)


class BargeInType(StrEnum):
    DISABLED = "disabled"
    WAKE_WORD = "wake_word"
    SPEECH = "speech"


class DisabledBargeInConfig(_ConfigModel):
    type: Literal[BargeInType.DISABLED] = BargeInType.DISABLED


class WakeWordBargeInConfig(_ConfigModel):
    type: Literal[BargeInType.WAKE_WORD] = BargeInType.WAKE_WORD


class SpeechBargeInConfig(_ConfigModel):
    type: Literal[BargeInType.SPEECH] = BargeInType.SPEECH
    min_level_dbfs: float = Field(default=-45.0, le=0.0)
    min_speech_probability: float = Field(default=0.6, gt=0.0, le=1.0)
    min_speech_seconds: float = Field(default=0.35, gt=0.0)
    max_echo_confidence: float = Field(default=0.5, gt=0.0, le=1.0)


BargeInConfig = Annotated[
    DisabledBargeInConfig | WakeWordBargeInConfig | SpeechBargeInConfig,
    Field(discriminator="type"),
]


class AudioOutputType(StrEnum):
    LOCAL = "local"
    SONOS = "sonos"


class LocalAudioOutputConfig(_ConfigModel):
    type: Literal[AudioOutputType.LOCAL] = AudioOutputType.LOCAL


class SonosAudioOutputConfig(_ConfigModel):
    type: Literal[AudioOutputType.SONOS] = AudioOutputType.SONOS


AudioOutputConfig = Annotated[
    LocalAudioOutputConfig | SonosAudioOutputConfig,
    Field(discriminator="type"),
]


class EchoCancellationConfig(_ConfigModel):
    enabled: bool = True
    sample_rate: int | None = Field(default=None, gt=0)
    reference_history_seconds: float = Field(default=8.0, gt=0.0)
    max_upload_echo_confidence: float = Field(default=0.5, gt=0.0, le=1.0)


class AudioConfig(_ConfigModel):
    output: AudioOutputConfig = Field(default_factory=LocalAudioOutputConfig)
    echo_cancellation: EchoCancellationConfig = Field(
        default_factory=EchoCancellationConfig
    )


class RecordingConfig(_ConfigModel):
    enabled: bool = False
    path: Path = Path("recordings/conversation.wav")


class ToggleConfig(_ConfigModel):
    enabled: bool = True


class HueConfig(_ConfigModel):
    enabled: bool = False
    room_name: str = Field(default="Mein Zimmer", min_length=1)


class SonosAudioFocusStrategy(StrEnum):
    DUCK = "duck"
    PAUSE = "pause"


class SonosAudioFocusConfig(_ConfigModel):
    enabled: bool = False
    strategy: SonosAudioFocusStrategy = SonosAudioFocusStrategy.DUCK


class IntegrationsConfig(_ConfigModel):
    sounds: ToggleConfig = Field(default_factory=ToggleConfig)
    tool_acknowledgements: ToggleConfig = Field(default_factory=ToggleConfig)
    hue: HueConfig = Field(default_factory=HueConfig)
    sonos_audio_focus: SonosAudioFocusConfig = Field(
        default_factory=SonosAudioFocusConfig
    )


class SonosConfig(_ConfigModel):
    ip_address: str = Field(min_length=1)
    local_host: str | None = None
    clip_volume_boost: int = Field(default=15, ge=0, le=100)
    clip_prebuffer_seconds: float = Field(default=0.25, ge=0.0)


class VoiceSessionConfig(BaseSettings):
    """Complete configuration for a device-side voice session."""

    model_config = SettingsConfigDict(
        env_prefix="CARA_",
        env_nested_delimiter="_",
        env_nested_max_split=1,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        yaml_file=DEFAULT_CONFIG_FILE,
    )

    gateway: GatewayConfig
    session: SessionConfig = Field(default_factory=SessionConfig)
    activation: ActivationConfig = Field(default_factory=ActivationConfig)
    barge_in: BargeInConfig = Field(default_factory=WakeWordBargeInConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    recording: RecordingConfig = Field(default_factory=RecordingConfig)
    integrations: IntegrationsConfig = Field(default_factory=IntegrationsConfig)
    sonos: SonosConfig | None = None

    @model_validator(mode="after")
    def validate_feature_dependencies(self) -> Self:
        needs_sonos = (
            self.audio.output.type is AudioOutputType.SONOS
            or self.integrations.sonos_audio_focus.enabled
        )
        if needs_sonos and self.sonos is None:
            raise ValueError(
                "sonos is required when audio.output.type is 'sonos' or "
                "integrations.sonos_audio_focus.enabled is true"
            )
        if (
            self.barge_in.type is BargeInType.WAKE_WORD
            and not self.activation.wake_word.enabled
        ):
            raise ValueError(
                "barge_in.type 'wake_word' requires activation.wake_word.enabled"
            )
        return self

    @classmethod
    def from_yaml(cls, path: str | Path = DEFAULT_CONFIG_FILE) -> Self:
        config_path = Path(path)
        if (
            config_path == DEFAULT_CONFIG_FILE
            and not config_path.is_file()
            and _LEGACY_CONFIG_FILE.is_file()
        ):
            config_path = _LEGACY_CONFIG_FILE
        if not config_path.is_file():
            raise VoiceConfigError(
                f"Voice configuration file was not found: {config_path.resolve()}"
            )
        try:
            document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as error:
            raise VoiceConfigError(
                f"Could not parse voice configuration {config_path.resolve()}: {error}"
            ) from error
        try:
            _validate_document_root(document)
        except VoiceConfigError as error:
            raise VoiceConfigError(
                f"Invalid voice configuration in {config_path.resolve()}: {error}"
            ) from error
        try:
            configured_model = type(
                "_ConfiguredVoiceSessionConfig",
                (cls,),
                {
                    "__module__": cls.__module__,
                    "model_config": SettingsConfigDict(
                        **{**cls.model_config, "yaml_file": config_path}
                    ),
                },
            )
            loaded = configured_model()
            return cast(Self, loaded)
        except ValidationError as error:
            details = "\n".join(
                _format_validation_error(item) for item in error.errors()
            )
            raise VoiceConfigError(
                f"Invalid voice configuration in {config_path.resolve()}:\n{details}"
            ) from error
        except SettingsError as error:
            cause = error.__cause__ or error
            raise VoiceConfigError(
                f"Could not parse voice configuration {config_path.resolve()}: {cause}"
            ) from error

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )


def _validate_document_root(document: object) -> None:
    if not isinstance(document, dict):
        raise VoiceConfigError("The YAML document must contain a mapping at its root.")
    known_fields = set(VoiceSessionConfig.model_fields)
    unknown_fields = sorted(set(document) - known_fields)
    if unknown_fields:
        rendered = ", ".join(str(field) for field in unknown_fields)
        raise VoiceConfigError(f"Unknown top-level configuration field(s): {rendered}")
    gateway = document.get("gateway")
    if isinstance(gateway, dict):
        known_gateway_fields = set(GatewayConfig.model_fields)
        unknown_gateway_fields = sorted(set(gateway) - known_gateway_fields)
        if unknown_gateway_fields:
            rendered = ", ".join(str(field) for field in unknown_gateway_fields)
            raise VoiceConfigError(
                f"Unknown configuration field(s) below gateway: {rendered}"
            )


def _format_validation_error(error: Mapping[str, Any]) -> str:
    location = ".".join(str(part) for part in error["loc"])
    message = str(error["msg"])
    value = error.get("input")
    sensitive = {"key", "password", "secret", "token"}
    if any(part in location.lower() for part in sensitive):
        value = "<redacted>"
    return f"  - {location}: {message} (received {value!r})"
