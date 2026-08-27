from pydantic import BaseModel, ConfigDict, Field

from voice.tts import DeepgramVoice


class TextToSpeechConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    voice: DeepgramVoice | str = DeepgramVoice.AURA_2_THALIA_EN
    sample_rate: int = Field(default=24_000, gt=0)
    segment_idle_seconds: float = Field(default=0.5, gt=0.0)
    reconnect_attempts: int = Field(default=1, ge=0)
