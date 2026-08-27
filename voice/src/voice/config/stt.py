from pydantic import BaseModel, ConfigDict, Field

_MICROPHONE_SAMPLE_RATE = 16_000


class SpeechToTextConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sample_rate: int = Field(default=_MICROPHONE_SAMPLE_RATE, gt=0)
    # Deepgram's own default of 5s is a phone-system timeout, not a
    # conversational one.
    eot_timeout_ms: int = Field(default=2_000, gt=0)
