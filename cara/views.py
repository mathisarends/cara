from pydantic import BaseModel, ConfigDict

from cara.speech import TextToSpeechVoice

DEFAULT_TTS_VOICE_INSTRUCTIONS = "Sprich freundlich, ruhig und klar auf Deutsch."


class SpeechConfig(BaseModel):
    """Language and voice settings shared by speech-to-text and text-to-speech."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    language: str = "de"
    tts_voice: TextToSpeechVoice = TextToSpeechVoice.MARIN
    tts_voice_instructions: str = DEFAULT_TTS_VOICE_INSTRUCTIONS
