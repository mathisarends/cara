from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class VoiceSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CARA_GATEWAY_VOICE_",
        extra="ignore",
        frozen=True,
    )

    deepgram_api_key: SecretStr = Field(min_length=1)
    stt_model: str = "flux-general-en"
    tts_model: str = "aura-2-thalia-en"
    language: str = "en"
    input_queue_size: int = Field(default=64, ge=1)
    text_queue_size: int = Field(default=8, ge=1)
    reconnect_window_seconds: float = Field(default=30, ge=0)
    conversation_follow_up_delay_seconds: float = Field(default=0.5, ge=0)
    conversation_inactivity_timeout_seconds: float = Field(default=5.0, gt=0)
    conversation_inactivity_countdown_seconds: int = Field(default=3, ge=0)
    recording_bit_rate_kbps: int = Field(default=64, gt=0)
