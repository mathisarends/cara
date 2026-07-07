import asyncio
import logging
from dataclasses import dataclass

from llmify import ChatModel, ChatOpenAI

from cara.audio import AudioPlayer, MicrophoneRecorder, SpeechRecorder, WavAudioPlayer
from cara.events import (
    AnswerGenerated,
    AssistantState,
    Event,
    EventBus,
    SessionEnded,
    SessionStarted,
    StateChanged,
    Transcribed,
    TurnCompleted,
    TurnStarted,
)
from cara.messages import MessageManager, SystemPrompt
from cara.speech import (
    OpenAISpeechToText,
    OpenAITextToSpeech,
    SpeechToTextRequest,
    TextToSpeechFormat,
    TextToSpeechRequest,
)

logger = logging.getLogger(__name__)


DEFAULT_SYSTEM_PROMPT = SystemPrompt().render()
DEFAULT_TTS_VOICE_INSTRUCTIONS = "Sprich freundlich, ruhig und klar auf Deutsch."
DEFAULT_FOLLOW_UP_TIMEOUT_SECONDS = 7.0
DEFAULT_MAX_MESSAGE_TURNS = 12
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
    message_manager: MessageManager


class VoiceAssistant:
    def __init__(
        self,
        *,
        llm: ChatModel | None = None,
        api_key: str | None = None,
        recorder: SpeechRecorder | None = None,
        player: AudioPlayer | None = None,
        event_bus: EventBus,
        language: str = "de",
        system_prompt: str | SystemPrompt | None = None,
        override_system_prompt: str | None = None,
        extend_system_prompt: str | None = None,
        tts_voice_instructions: str = DEFAULT_TTS_VOICE_INSTRUCTIONS,
        follow_up_timeout_seconds: float = DEFAULT_FOLLOW_UP_TIMEOUT_SECONDS,
        max_message_turns: int = DEFAULT_MAX_MESSAGE_TURNS,
    ) -> None:
        self._llm = llm or ChatOpenAI()
        self._recorder = recorder or MicrophoneRecorder()
        self._player = player or WavAudioPlayer()
        self._stt = OpenAISpeechToText(api_key)
        self._tts = OpenAITextToSpeech(api_key)
        self._language = language
        self._system_prompt = self._build_system_prompt(
            system_prompt=system_prompt,
            override_system_prompt=override_system_prompt,
            extend_system_prompt=extend_system_prompt,
        )
        self._tts_voice_instructions = tts_voice_instructions
        self._follow_up_timeout_seconds = follow_up_timeout_seconds
        self._max_message_turns = max_message_turns
        self._event_bus = event_bus
        self._state = AssistantState.IDLE

    @property
    def state(self) -> AssistantState:
        return self._state

    def _build_system_prompt(
        self,
        *,
        system_prompt: str | SystemPrompt | None,
        override_system_prompt: str | None,
        extend_system_prompt: str | None,
    ) -> str | SystemPrompt:
        if system_prompt is not None and (override_system_prompt is not None or extend_system_prompt is not None):
            raise ValueError("Use system_prompt or override_system_prompt/extend_system_prompt, not both.")
        if system_prompt is not None:
            return system_prompt
        return SystemPrompt(
            override_system_prompt=override_system_prompt,
            extend_system_prompt=extend_system_prompt,
        )

    async def run_session(self) -> VoiceSession:
        message_manager = MessageManager(
            system_prompt=self._system_prompt,
            max_turns=self._max_message_turns,
        )
        turns: list[VoiceTurn] = []
        await self._emit(SessionStarted())
        try:
            while True:
                turn = await self.run_turn(
                    message_manager=message_manager,
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
        return VoiceSession(turns=turns, message_manager=message_manager)

    async def run_turn(
        self,
        message_manager: MessageManager | None = None,
        *,
        follow_up: bool = False,
        reset_state: bool = True,
        interrupt: asyncio.Event | None = None,
    ) -> VoiceTurn | None:
        if message_manager is None:
            message_manager = MessageManager(
                system_prompt=self._system_prompt,
                max_turns=self._max_message_turns,
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

            message_manager.add_user(transcript)
            answer = await self._think(message_manager, interrupt=interrupt)
            message_manager.add_assistant(answer)
            answer_audio = await self._speak(answer, interrupt=interrupt)

            turn = VoiceTurn(
                transcript=transcript,
                answer=answer,
                utterance_audio=utterance_audio,
                answer_audio=answer_audio,
            )
            await self._emit(TurnCompleted(turn=turn))
            return turn
        finally:
            if reset_state:
                await self._set_state(AssistantState.IDLE)

    async def _record(self, *, follow_up: bool = False) -> bytes | None:
        if follow_up:
            await self._set_state(AssistantState.WAITING_FOLLOW_UP)
            return await self._recorder.record_until_silence(
                initial_silence_timeout=self._follow_up_timeout_seconds,
            )
        await self._set_state(AssistantState.LISTENING)
        return await self._recorder.record_until_silence()

    async def _transcribe(self, utterance_audio: bytes) -> str:
        await self._set_state(AssistantState.TRANSCRIBING)
        response = await self._stt.transcribe(SpeechToTextRequest(audio=utterance_audio, language=self._language))
        transcript = response.text.strip()
        if transcript:
            logger.info("User said: %s", transcript)
            await self._emit(Transcribed(transcript=transcript))
        return transcript

    async def _think(self, message_manager: MessageManager, *, interrupt: asyncio.Event | None = None) -> str:
        await self._set_state(AssistantState.THINKING)
        if interrupt is None:
            answer = await self._reply(message_manager)
        else:
            reply_task = asyncio.create_task(self._reply(message_manager))
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
        await self._emit(AnswerGenerated(answer=answer))
        return answer

    async def _speak(self, answer: str, *, interrupt: asyncio.Event | None = None) -> bytes:
        await self._set_state(AssistantState.SPEAKING)
        response = await self._tts.synthesize(
            TextToSpeechRequest(
                text=answer,
                response_format=TextToSpeechFormat.WAV,
                instructions=self._tts_voice_instructions,
            )
        )
        await self._player.play(response.audio, cancel=interrupt)
        return response.audio

    async def _reply(self, message_manager: MessageManager) -> str:
        result = await self._llm.invoke(message_manager.to_llm_messages())
        return result.completion.strip()

    def _should_end_session(self, turn: VoiceTurn) -> bool:
        transcript = turn.transcript.casefold()
        return any(phrase in transcript for phrase in SESSION_END_PHRASES)

    async def _set_state(self, state: AssistantState) -> None:
        self._state = state
        await self._emit(StateChanged(state=state))

    async def _emit(self, event: Event) -> None:
        await self._event_bus.dispatch(event)
