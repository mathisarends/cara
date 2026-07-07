from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from llmify import ChatModel, ChatOpenAI

from cara.audio import AudioPlayer, MicrophoneRecorder, SpeechRecorder, WavAudioPlayer
from cara.conversation import Conversation
from cara.events import EventBus
from cara.lifecycle import (
    AnswerGenerated,
    AssistantEvent,
    AssistantState,
    SessionEnded,
    SessionStarted,
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
DEFAULT_FOLLOW_UP_TIMEOUT_SECONDS = 7.0
DEFAULT_MAX_CONVERSATION_TURNS = 12
SESSION_END_PHRASES = (
    "das war's",
    "das wars",
    "danke das war's",
    "danke das wars",
    "tschüss",
    "tschuess",
    "auf wiedersehen",
    "stop",
    "stopp",
    "ende",
    "beenden",
    "goodbye",
)


@dataclass(frozen=True)
class VoiceTurn:
    transcript: str
    answer: str
    utterance_audio: bytes
    answer_audio: bytes


@dataclass(frozen=True)
class VoiceSession:
    turns: list[VoiceTurn]
    conversation: Conversation


class VoiceAssistant:
    def __init__(
        self,
        *,
        llm: ChatModel | None = None,
        client: AsyncOpenAI | None = None,
        recorder: SpeechRecorder | None = None,
        player: AudioPlayer | None = None,
        event_bus: EventBus,
        language: str = "de",
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        tts_voice_instructions: str = DEFAULT_TTS_VOICE_INSTRUCTIONS,
        follow_up_timeout_seconds: float = DEFAULT_FOLLOW_UP_TIMEOUT_SECONDS,
        max_conversation_turns: int = DEFAULT_MAX_CONVERSATION_TURNS,
    ) -> None:
        openai_client = resolve_openai_client(client)
        self._llm = llm or ChatOpenAI()
        self._recorder = recorder or MicrophoneRecorder()
        self._player = player or WavAudioPlayer()
        self._stt = AsyncOpenAISpeechToText(openai_client)
        self._tts = AsyncOpenAITextToSpeech(openai_client)
        self.language = language
        self.system_prompt = system_prompt
        self.tts_voice_instructions = tts_voice_instructions
        self.follow_up_timeout_seconds = follow_up_timeout_seconds
        self._max_conversation_turns = max_conversation_turns
        self._event_bus = event_bus
        self._state = AssistantState.IDLE

    @property
    def state(self) -> AssistantState:
        return self._state

    async def run_session(self) -> VoiceSession:
        conversation = Conversation(
            system_prompt=self.system_prompt,
            max_turns=self._max_conversation_turns,
        )
        turns: list[VoiceTurn] = []
        await self._emit(SessionStarted())
        try:
            while True:
                turn = await self.run_turn(
                    conversation=conversation,
                    follow_up=bool(turns),
                    reset_state=False,
                )
                if turn is None:
                    break
                turns.append(turn)
                if self._should_end_session(turn):
                    break
        finally:
            await self._emit(SessionEnded())
            await self._set_state(AssistantState.IDLE)
        return VoiceSession(turns=turns, conversation=conversation)

    async def run_turn(
        self,
        conversation: Conversation | None = None,
        *,
        follow_up: bool = False,
        reset_state: bool = True,
        interrupt: asyncio.Event | None = None,
    ) -> VoiceTurn | None:
        if conversation is None:
            conversation = Conversation(
                system_prompt=self.system_prompt,
                max_turns=self._max_conversation_turns,
            )
        try:
            await self._emit(TurnStarted())

            utterance_audio = await self._record(follow_up=follow_up)
            if utterance_audio is None:
                return None
            transcript = await self._transcribe(utterance_audio)
            if not transcript:
                logger.info("Ignoring empty transcription")
                return None

            conversation.add_user(transcript)
            answer = await self._think(conversation, interrupt=interrupt)
            conversation.add_assistant(answer)
            answer_audio = await self._speak(answer, interrupt=interrupt)

            turn = VoiceTurn(
                transcript=transcript,
                answer=answer,
                utterance_audio=utterance_audio,
                answer_audio=answer_audio,
            )
            await self._emit(TurnCompleted(turn))
            return turn
        finally:
            if reset_state:
                await self._set_state(AssistantState.IDLE)

    async def _record(self, *, follow_up: bool = False) -> bytes | None:
        if follow_up:
            await self._set_state(AssistantState.WAITING_FOLLOW_UP)
            return await self._recorder.record_until_silence(
                initial_silence_timeout=self.follow_up_timeout_seconds,
            )
        await self._set_state(AssistantState.LISTENING)
        return await self._recorder.record_until_silence()

    async def _transcribe(self, utterance_audio: bytes) -> str:
        await self._set_state(AssistantState.TRANSCRIBING)
        response = await self._stt.transcribe(
            SpeechToTextRequest(audio=utterance_audio, language=self.language)
        )
        transcript = response.text.strip()
        if transcript:
            logger.info("User said: %s", transcript)
            await self._emit(Transcribed(transcript))
        return transcript

    async def _think(self, conversation: Conversation, *, interrupt: asyncio.Event | None = None) -> str:
        await self._set_state(AssistantState.THINKING)
        if interrupt is None:
            answer = await self._reply(conversation)
        else:
            reply_task = asyncio.create_task(self._reply(conversation))
            interrupt_task = asyncio.create_task(interrupt.wait())
            done, pending = await asyncio.wait(
                {reply_task, interrupt_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            if interrupt_task in done and interrupt.is_set():
                reply_task.cancel()
                raise asyncio.CancelledError("Assistant thinking was interrupted.")
            answer = await reply_task
        logger.info("Assistant answer: %s", answer)
        await self._emit(AnswerGenerated(answer))
        return answer

    async def _speak(self, answer: str, *, interrupt: asyncio.Event | None = None) -> bytes:
        await self._set_state(AssistantState.SPEAKING)
        response = await self._tts.synthesize(
            TextToSpeechRequest(
                text=answer,
                response_format=TextToSpeechFormat.WAV,
                instructions=self.tts_voice_instructions,
            )
        )
        await self._player.play(response.audio, cancel=interrupt)
        return response.audio

    async def _reply(self, conversation: Conversation) -> str:
        result = await self._llm.invoke(conversation.to_llm_messages())
        return result.completion.strip()

    def _should_end_session(self, turn: VoiceTurn) -> bool:
        transcript = turn.transcript.casefold()
        return any(phrase in transcript for phrase in SESSION_END_PHRASES)

    async def _set_state(self, state: AssistantState) -> None:
        self._state = state
        await self._emit(StateChanged(state))

    async def _emit(self, event: AssistantEvent) -> None:
        await self._event_bus.dispatch(event)
