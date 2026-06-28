from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from llmify import ChatModel, ChatOpenAI, SystemMessage, UserMessage

from cara.audio import AudioPlayer, MicrophoneRecorder, UtteranceRecorder, WavAudioPlayer
from cara.lifecycle import (
    AnswerGenerated,
    AssistantEvent,
    AssistantLifecycleListener,
    AssistantState,
    StateChanged,
    Transcribed,
    TurnCompleted,
    TurnStarted,
)
from cara.speech import (
    AsyncOpenAISpeechToText,
    AsyncOpenAITextToSpeech,
    SpeechToTextRequest,
    TextToSpeechFormat,
    TextToSpeechRequest,
)
from cara.speech._client import resolve_openai_client

if TYPE_CHECKING:
    from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


DEFAULT_SYSTEM_PROMPT = (
    "Du bist Cara, ein knapper deutschsprachiger Voice Assistant. "
    "Antworte natürlich, kurz und direkt. Stelle Rückfragen, wenn Informationen fehlen."
)
DEFAULT_TTS_VOICE_INSTRUCTIONS = "Sprich freundlich, ruhig und klar auf Deutsch."


@dataclass(frozen=True)
class VoiceTurn:
    transcript: str
    answer: str
    utterance_audio: bytes
    answer_audio: bytes


class VoiceAssistant:
    def __init__(
        self,
        *,
        llm: ChatModel | None = None,
        client: AsyncOpenAI | None = None,
        recorder: UtteranceRecorder | None = None,
        player: AudioPlayer | None = None,
        listeners: Sequence[AssistantLifecycleListener] | None = None,
        language: str = "de",
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        tts_voice_instructions: str = DEFAULT_TTS_VOICE_INSTRUCTIONS,
    ) -> None:
        openai_client = resolve_openai_client(client)
        self.llm = llm or ChatOpenAI()
        self.recorder = recorder or MicrophoneRecorder()
        self.player = player or WavAudioPlayer()
        self.stt = AsyncOpenAISpeechToText(openai_client)
        self.tts = AsyncOpenAITextToSpeech(openai_client)
        self.language = language
        self.system_prompt = system_prompt
        self.tts_voice_instructions = tts_voice_instructions
        self._listeners: list[AssistantLifecycleListener] = list(listeners or [])
        self._state = AssistantState.IDLE

    @property
    def state(self) -> AssistantState:
        return self._state

    def add_listener(self, listener: AssistantLifecycleListener) -> None:
        """Register a listener so it receives lifecycle events for future turns."""
        self._listeners.append(listener)

    async def run_turn(self) -> VoiceTurn | None:
        try:
            await self._emit(TurnStarted())

            utterance_audio = await self._record()
            transcript = await self._transcribe(utterance_audio)
            if not transcript:
                logger.info("Ignoring empty transcription")
                return None

            answer = await self._think(transcript)
            answer_audio = await self._speak(answer)

            turn = VoiceTurn(
                transcript=transcript,
                answer=answer,
                utterance_audio=utterance_audio,
                answer_audio=answer_audio,
            )
            await self._emit(TurnCompleted(turn))
            return turn
        finally:
            await self._set_state(AssistantState.IDLE)

    async def _record(self) -> bytes:
        await self._set_state(AssistantState.LISTENING)
        return await self.recorder.record_until_silence()

    async def _transcribe(self, utterance_audio: bytes) -> str:
        await self._set_state(AssistantState.TRANSCRIBING)
        response = await self.stt.transcribe(
            SpeechToTextRequest(audio=utterance_audio, language=self.language)
        )
        transcript = response.text.strip()
        if transcript:
            logger.info("User said: %s", transcript)
            await self._emit(Transcribed(transcript))
        return transcript

    async def _think(self, transcript: str) -> str:
        await self._set_state(AssistantState.THINKING)
        answer = await self._reply(transcript)
        logger.info("Assistant answer: %s", answer)
        await self._emit(AnswerGenerated(answer))
        return answer

    async def _speak(self, answer: str) -> bytes:
        await self._set_state(AssistantState.SPEAKING)
        response = await self.tts.synthesize(
            TextToSpeechRequest(
                text=answer,
                response_format=TextToSpeechFormat.WAV,
                instructions=self.tts_voice_instructions,
            )
        )
        await self.player.play(response.audio)
        return response.audio

    async def _reply(self, transcript: str) -> str:
        result = await self.llm.invoke(
            [
                SystemMessage(content=self.system_prompt),
                UserMessage(content=transcript),
            ]
        )
        return result.completion.strip()

    async def _set_state(self, state: AssistantState) -> None:
        self._state = state
        await self._emit(StateChanged(state))

    async def _emit(self, event: AssistantEvent) -> None:
        for listener in self._listeners:
            try:
                await listener.on_event(event)
            except Exception:
                logger.exception("Lifecycle listener %r failed handling %r", listener, event)
