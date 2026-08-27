from typing import assert_never

from voice.barge_in import BargeInStrategy, NoBargeIn, SpeechBargeIn, WakeWordBargeIn
from voice.config.barge_in import (
    BargeInConfig,
    NoBargeInConfig,
    SpeechBargeInConfig,
    WakeWordBargeInConfig,
)
from voice.config.stt import SpeechToTextConfig
from voice.config.tts import TextToSpeechConfig
from voice.stt import DeepgramSpeechToText, SpeechToText
from voice.tts import DeepgramTextToSpeech, TextToSpeech


def build_text_to_speech(config: TextToSpeechConfig) -> TextToSpeech:
    return DeepgramTextToSpeech(
        voice=config.voice,
        sample_rate=config.sample_rate,
        segment_idle_seconds=config.segment_idle_seconds,
        reconnect_attempts=config.reconnect_attempts,
    )


def build_speech_to_text(config: SpeechToTextConfig) -> SpeechToText:
    return DeepgramSpeechToText(
        sample_rate=config.sample_rate,
        eot_timeout_ms=config.eot_timeout_ms,
    )


def build_barge_in(config: BargeInConfig) -> BargeInStrategy:
    match config:
        case SpeechBargeInConfig():
            return SpeechBargeIn(
                min_level_dbfs=config.min_level_dbfs,
                min_speech_probability=config.min_speech_probability,
                min_speech_seconds=config.min_speech_seconds,
            )
        case WakeWordBargeInConfig():
            return WakeWordBargeIn()
        case NoBargeInConfig():
            return NoBargeIn()
        case _:
            assert_never(config)
