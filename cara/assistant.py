import logging
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from cara.audio import MicrophoneRecorder, WavAudioPlayer
from cara.speech import (
    AsyncOpenAISpeechToText,
    AsyncOpenAITextToSpeech,
    SpeechToTextRequest,
    TextToSpeechFormat,
    TextToSpeechRequest,
)
from cara.speech._client import resolve_openai_client

logger = logging.getLogger(__name__)


class UtteranceRecorder(Protocol):
    async def record_until_silence(self) -> Path: ...


class AudioPlayer(Protocol):
    async def play(self, audio_path: str | Path) -> None: ...


@dataclass(frozen=True)
class AssistantConfig:
    llm_model: str = "gpt-4.1-mini"
    language: str = "de"
    system_prompt: str = (
        "Du bist Cara, ein knapper deutschsprachiger Voice Assistant. "
        "Antworte natürlich, kurz und direkt. Stelle Rückfragen, wenn Informationen fehlen."
    )
    tts_output_dir: Path = Path(tempfile.gettempdir()) / "cara"


@dataclass(frozen=True)
class VoiceTurn:
    audio_path: Path
    transcript: str
    answer: str
    speech_path: Path


class AsyncOpenAIChat:
    """Small wrapper around OpenAI Responses for one-shot assistant replies."""

    def __init__(self, client: Any | None = None, model: str = "gpt-4.1-mini") -> None:
        self.client = resolve_openai_client(client)
        self.model = model

    async def reply(self, transcript: str, instructions: str) -> str:
        result = await self.client.responses.create(
            model=self.model,
            instructions=instructions,
            input=transcript,
        )
        return _extract_response_text(result)


class VoiceAssistant:
    def __init__(
        self,
        *,
        client: Any | None = None,
        recorder: UtteranceRecorder | None = None,
        player: AudioPlayer | None = None,
        config: AssistantConfig | None = None,
    ) -> None:
        self.config = config or AssistantConfig()
        openai_client = resolve_openai_client(client)
        self.recorder = recorder or MicrophoneRecorder()
        self.player = player or WavAudioPlayer()
        self.stt = AsyncOpenAISpeechToText(openai_client)
        self.chat = AsyncOpenAIChat(openai_client, model=self.config.llm_model)
        self.tts = AsyncOpenAITextToSpeech(openai_client)

    async def handle_wake_word(self) -> VoiceTurn | None:
        audio_path = await self.recorder.record_until_silence()
        transcript_response = await self.stt.transcribe(
            SpeechToTextRequest(audio_path=audio_path, language=self.config.language)
        )
        transcript = transcript_response.text.strip()
        if not transcript:
            logger.info("Ignoring empty transcription from %s", audio_path)
            return None

        logger.info("User said: %s", transcript)
        answer = await self.chat.reply(transcript, instructions=self.config.system_prompt)
        logger.info("Assistant answer: %s", answer)

        speech_path = self.config.tts_output_dir / f"answer-{int(time.time() * 1000)}.wav"
        await self.tts.synthesize_to_file(
            TextToSpeechRequest(
                text=answer,
                response_format=TextToSpeechFormat.WAV,
                instructions="Sprich freundlich, ruhig und klar auf Deutsch.",
            ),
            speech_path,
        )
        await self.player.play(speech_path)
        return VoiceTurn(
            audio_path=audio_path,
            transcript=transcript,
            answer=answer,
            speech_path=speech_path,
        )


def _extract_response_text(result: Any) -> str:
    output_text = getattr(result, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    if isinstance(result, dict):
        output_text = result.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()
        output = result.get("output")
    else:
        output = getattr(result, "output", None)

    parts: list[str] = []
    if isinstance(output, list):
        for item in output:
            content = item.get("content") if isinstance(item, dict) else getattr(item, "content", None)
            if not isinstance(content, list):
                continue
            for block in content:
                text = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
                if isinstance(text, str):
                    parts.append(text)

    text = "".join(parts).strip()
    if text:
        return text
    raise TypeError("OpenAI response did not contain assistant text")
