import asyncio
import json
import logging

from llmify import ChatInvokeCompletion, ChatModel, ChatOpenAI

from cara.audio import AudioPlayer, MicrophoneRecorder, SpeechRecorder, WavAudioPlayer
from cara.events import (
    AnswerGenerated,
    AssistantState,
    EventBus,
    SessionEnded,
    SessionStarted,
    StateChanged,
    Transcribed,
    TurnStarted,
)
from cara.messages import MessageManager, SystemPrompt
from cara.speech import (
    OpenAISpeechToText,
    OpenAITextToSpeech,
    SpeechToText,
    SpeechToTextRequest,
    TextToSpeech,
    TextToSpeechFormat,
    TextToSpeechRequest,
)
from cara.tools import ActionKind, Tools
from cara.views import SpeechConfig

logger = logging.getLogger(__name__)


DEFAULT_FOLLOW_UP_TIMEOUT_SECONDS = 7.0


class VoiceAssistant:
    def __init__(
        self,
        *,
        llm: ChatModel | None = None,
        api_key: str | None = None,
        recorder: SpeechRecorder | None = None,
        player: AudioPlayer | None = None,
        stt: SpeechToText | None = None,
        tts: TextToSpeech | None = None,
        event_bus: EventBus,
        tools: Tools | None = None,
        speech_config: SpeechConfig | None = None,
        system_prompt: str | SystemPrompt | None = None,
        override_system_prompt: str | None = None,
        extend_system_prompt: str | None = None,
        follow_up_timeout_seconds: float = DEFAULT_FOLLOW_UP_TIMEOUT_SECONDS,
    ) -> None:
        self._llm = llm or ChatOpenAI()
        self._recorder = recorder or MicrophoneRecorder()
        self._player = player or WavAudioPlayer()
        self._stt = stt or OpenAISpeechToText(api_key)
        self._tts = tts or OpenAITextToSpeech(api_key)
        self._tools = tools or Tools()
        self._speech_config = speech_config or SpeechConfig()
        self._system_prompt = self._build_system_prompt(
            system_prompt=system_prompt,
            override_system_prompt=override_system_prompt,
            extend_system_prompt=extend_system_prompt,
        )
        self._message_manager = MessageManager(system_prompt=self._system_prompt)
        self._follow_up_timeout_seconds = follow_up_timeout_seconds
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

    async def run(self) -> None:
        follow_up = False
        await self._event_bus.dispatch(SessionStarted())
        try:
            while True:
                await self._event_bus.dispatch(TurnStarted())

                utterance_audio = await self._record(follow_up=follow_up)
                if utterance_audio is None:
                    break
                transcript = await self._transcribe(utterance_audio)
                if not transcript:
                    logger.info("Ignoring empty transcription")
                    break

                self._message_manager.add_user(transcript)
                answer, end_session = await self._think()
                self._message_manager.add_assistant(answer)
                await self._speak(answer)

                if end_session:
                    break
                follow_up = True
        finally:
            await self._event_bus.dispatch(SessionEnded())
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
        response = await self._stt.transcribe(
            SpeechToTextRequest(audio=utterance_audio, language=self._speech_config.language)
        )
        transcript = response.text.strip()
        if transcript:
            logger.info("User said: %s", transcript)
            await self._event_bus.dispatch(Transcribed(transcript=transcript))
        return transcript

    async def _think(self, *, interrupt: asyncio.Event | None = None) -> tuple[str, bool]:
        await self._set_state(AssistantState.THINKING)
        completion = await self._invoke_llm(interrupt=interrupt)
        answer, end_session = await self._resolve_completion(completion)
        logger.info("Assistant answer: %s", answer)
        await self._event_bus.dispatch(AnswerGenerated(answer=answer))
        return answer, end_session

    async def _invoke_llm(self, *, interrupt: asyncio.Event | None) -> ChatInvokeCompletion[str]:
        if interrupt is None:
            return await self._reply()

        reply_task = asyncio.create_task(self._reply())
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
        return await reply_task

    async def _resolve_completion(self, completion: ChatInvokeCompletion[str]) -> tuple[str, bool]:
        answer = completion.completion.strip()
        end_session = False
        for tool_call in completion.tool_calls:
            arguments = json.loads(tool_call.function.arguments or "{}")
            result = await self._tools.execute(tool_call.function.name, arguments)
            tool = self._tools.get(tool_call.function.name)
            if tool is not None and tool.kind is ActionKind.END_SESSION:
                end_session = True
                if result.content:
                    answer = result.content.strip()
        return answer, end_session

    async def _speak(self, answer: str, *, interrupt: asyncio.Event | None = None) -> bytes:
        await self._set_state(AssistantState.SPEAKING)
        response = await self._tts.synthesize(
            TextToSpeechRequest(
                text=answer,
                voice=self._speech_config.tts_voice,
                response_format=TextToSpeechFormat.WAV,
                instructions=self._speech_config.tts_voice_instructions,
            )
        )
        await self._player.play(response.audio, cancel=interrupt)
        return response.audio

    async def _reply(self) -> ChatInvokeCompletion[str]:
        return await self._llm.invoke(
            self._message_manager.to_llm_messages(),
            tools=self._tools.to_schema(),
        )

    async def _set_state(self, state: AssistantState) -> None:
        self._state = state
        await self._event_bus.dispatch(StateChanged(state=state))
