import asyncio
import json
import logging
import threading
from collections.abc import AsyncIterator

from llmify import ChatInvokeCompletion, ChatModel, ChatOpenAI, StreamEvent, ToolCall

from cara.audio import (
    AudioPlayer,
    Earcon,
    EarconPlayer,
    MicrophoneRecorder,
    MicrophoneStream,
    SpeechRecorder,
    WavAudioPlayer,
)
from cara.audio.device import PortAudioDevice
from cara.console_logging import _log_user_transcript
from cara.events import (
    AnswerGenerated,
    AssistantState,
    EventBus,
    Interrupted,
    SessionEnded,
    SessionStarted,
    StateChanged,
    Transcribed,
    TurnStarted,
)
from cara.file_system import FileSystem
from cara.listener import SoundListener
from cara.llm import LanguageModels
from cara.messages import MessageManager, SystemPrompt
from cara.replies import StreamingReply
from cara.skills import Skills
from cara.speech import (
    OpenAISpeechToText,
    OpenAITextToSpeech,
    SpeechToText,
    SpeechToTextRequest,
    TextToSpeech,
)
from cara.speech.streaming import NaturalPauseChunker, StreamingTextToSpeech
from cara.tools import ActionKind, Tools
from cara.tools.handler import IpLocationClient, OpenMeteoClient, TavilySearchClient
from cara.views import SpeechSettings
from cara.wakeword import WakeWordListener, WakeWordSettings
from cara.wakeword.barge_in import WakeWordBargeIn

logger = logging.getLogger(__name__)

DEFAULT_FOLLOW_UP_TIMEOUT_SECONDS = 7.0


class _ResponseInterrupted(Exception):
    pass


class VoiceAssistant:
    def __init__(
        self,
        *,
        llm: ChatModel | None = None,
        models: LanguageModels | None = None,
        api_key: str | None = None,
        recorder: SpeechRecorder | None = None,
        player: AudioPlayer | None = None,
        stt: SpeechToText | None = None,
        tts: TextToSpeech | None = None,
        event_bus: EventBus | None = None,
        wake_word_settings: WakeWordSettings,
        tools: Tools | None = None,
        skills: Skills | None = None,
        file_system: FileSystem | None = None,
        speech_settings: SpeechSettings | None = None,
        system_prompt: str | SystemPrompt | None = None,
        override_system_prompt: str | None = None,
        extend_system_prompt: str | None = None,
        follow_up_timeout_seconds: float = DEFAULT_FOLLOW_UP_TIMEOUT_SECONDS,
    ) -> None:
        if models is not None and llm is not None:
            raise ValueError("Use models or llm, not both.")
        self._models = models or LanguageModels.single(
            llm or ChatOpenAI(model="gpt-5.6-terra", reasoning_effort="none")
        )
        self._audio_device = PortAudioDevice()
        self._microphone = MicrophoneStream(device=self._audio_device)
        self._recorder = recorder or MicrophoneRecorder(self._microphone)
        self._player = player or AudioPlayer(WavAudioPlayer(device=self._audio_device))
        self._stt = stt or OpenAISpeechToText(api_key)
        tts = tts or OpenAITextToSpeech(api_key)
        self._tools = tools or Tools()
        self._tools.provide(self._models, self._player, IpLocationClient(), OpenMeteoClient(), TavilySearchClient())
        if skills is not None:
            self._tools.provide(skills)
        if file_system is not None:
            self._tools.provide(file_system)
        self._speech_settings = speech_settings or SpeechSettings()
        self._speech_stream = StreamingTextToSpeech(
            tts=tts,
            player=self._player,
            voice=self._speech_settings.tts_voice,
            instructions=self._speech_settings.tts_voice_instructions,
        )
        self._wake_word_settings = wake_word_settings
        self._system_prompt = self._build_system_prompt(
            system_prompt=system_prompt,
            override_system_prompt=override_system_prompt,
            extend_system_prompt=extend_system_prompt,
        )
        self._message_manager = MessageManager(
            system_prompt=self._system_prompt,
            skills=skills,
        )
        self._follow_up_timeout_seconds = follow_up_timeout_seconds
        self._event_bus = event_bus or EventBus()
        self._earcons = EarconPlayer(self._player)
        self._sound_listener = SoundListener(self._event_bus, self._earcons)
        self._state = AssistantState.IDLE

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

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

    async def start(self) -> None:
        listener = WakeWordListener(
            self._microphone,
            wake_word=self._wake_word_settings.wake_word,
            sensitivity=self._wake_word_settings.sensitivity,
        )
        try:
            async for _ in listener.detections():
                await self._run(listener)
        finally:
            self._microphone.close()
            self._audio_device.close()

    async def _run(self, wake_word_listener: WakeWordListener) -> None:
        follow_up = False
        pending_audio: bytes | None = None
        ready: threading.Event | None = threading.Event()
        await self._event_bus.dispatch(SessionStarted())
        wake_earcon = asyncio.create_task(self._announce_wake(ready))
        try:
            while True:
                await self._event_bus.dispatch(TurnStarted())

                audio = pending_audio
                pending_audio = None
                if audio is None:
                    audio = await self._record(follow_up=follow_up, ready=ready)
                    ready = None
                if audio is None:
                    break
                transcript = await self._transcribe(audio)
                if not transcript:
                    logger.info("Ignoring empty transcription")
                    break

                self._message_manager.add_user(transcript)
                async with WakeWordBargeIn(wake_word_listener) as barge_in:
                    try:
                        answer, end_session = await self._think(interrupt=barge_in.interrupt)
                    except _ResponseInterrupted:
                        pending_audio = await self._receive_barge_in(phase=self._state)
                        if pending_audio is None:
                            break
                        follow_up = False
                        continue
                if barge_in.interrupt.is_set():
                    pending_audio = await self._receive_barge_in(phase=self._state)
                    if pending_audio is None:
                        break
                    follow_up = False
                    continue
                self._message_manager.add_assistant(answer)

                if end_session:
                    break
                follow_up = True
        finally:
            wake_earcon.cancel()
            await asyncio.gather(wake_earcon, return_exceptions=True)
            await self._event_bus.dispatch(SessionEnded())
            await self._set_state(AssistantState.IDLE)

    async def _announce_wake(self, ready: threading.Event) -> None:
        try:
            await self._earcons.play(Earcon.WAKE)
        finally:
            ready.set()

    async def _receive_barge_in(
        self,
        *,
        phase: AssistantState,
    ) -> bytes | None:
        await self._event_bus.dispatch(Interrupted(phase=phase))
        return await self._record()

    async def _record(
        self,
        *,
        follow_up: bool = False,
        ready: threading.Event | None = None,
    ) -> bytes | None:
        if follow_up:
            await self._set_state(AssistantState.WAITING_FOLLOW_UP)
            return await self._recorder.record_until_silence(
                initial_silence_timeout=self._follow_up_timeout_seconds,
                ready=ready,
            )
        await self._set_state(AssistantState.LISTENING)
        return await self._recorder.record_until_silence(ready=ready)

    async def _transcribe(self, audio: bytes) -> str:
        await self._set_state(AssistantState.TRANSCRIBING)
        response = await self._stt.transcribe(SpeechToTextRequest(audio=audio, language=self._speech_settings.language))
        transcript = response.text.strip()
        if transcript:
            _log_user_transcript(logger, transcript)
            await self._event_bus.dispatch(Transcribed(transcript=transcript))
        return transcript

    async def _think(self, *, interrupt: asyncio.Event | None = None) -> tuple[str, bool]:
        await self._set_state(AssistantState.THINKING)
        if interrupt is None:
            return await self._stream_response()

        response_task = asyncio.create_task(self._stream_response(interrupt=interrupt))
        interrupt_task = asyncio.create_task(interrupt.wait())
        try:
            done, _ = await asyncio.wait(
                {response_task, interrupt_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if interrupt_task in done and interrupt.is_set():
                raise _ResponseInterrupted
            return await response_task
        finally:
            for task in (response_task, interrupt_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(response_task, interrupt_task, return_exceptions=True)

    async def _stream_response(self, *, interrupt: asyncio.Event | None = None) -> tuple[str, bool]:
        while True:
            reply = StreamingReply(
                self._reply(),
                NaturalPauseChunker(
                    min_chunk_chars=300,
                    target_chunk_chars=500,
                    max_chunk_chars=800,
                ),
            )
            async with asyncio.TaskGroup() as task_group:
                reply_task = task_group.create_task(self._resolve_streaming_reply(reply))
                task_group.create_task(self._speak(reply.text_chunks, interrupt=interrupt))

            answer, end_session, called_tools = reply_task.result()
            if end_session or not called_tools:
                await self._event_bus.dispatch(AnswerGenerated(answer=answer))
                return answer, end_session
            await self._set_state(AssistantState.THINKING)

    async def _resolve_streaming_reply(self, reply: StreamingReply) -> tuple[str, bool, bool]:
        try:
            completion = await reply.collect()
            answer, end_session, called_tools = await self._resolve_completion(completion)
            reply.finish(answer)
            return answer, end_session, called_tools
        finally:
            reply.close()

    async def _resolve_completion(
        self,
        completion: ChatInvokeCompletion[str],
    ) -> tuple[str, bool, bool]:
        answer = completion.completion.strip()
        end_session = False
        tool_results: list[tuple[ToolCall, str]] = []
        for tool_call in completion.tool_calls:
            name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments or "{}")
            tool = self._tools.get(name)

            await self._set_state(AssistantState.CALLING_TOOL)
            result = await self._tools.execute(name, arguments)
            content = result.content or ("Tool completed successfully." if result.ok else "Tool failed.")
            tool_results.append((tool_call, content))
            if tool is not None and tool.kind is ActionKind.END_SESSION:
                end_session = True
                if result.content:
                    answer = result.content.strip()

        self._message_manager.add_tool_results(tool_results)
        return answer, end_session, bool(completion.tool_calls)

    async def _speak(
        self,
        sentences: AsyncIterator[str],
        *,
        interrupt: asyncio.Event | None = None,
    ) -> None:
        await self._speech_stream.speak(
            sentences,
            cancel=interrupt,
            on_started=lambda: self._set_state(AssistantState.SPEAKING),
        )

    async def _reply(self) -> AsyncIterator[StreamEvent]:
        async for event in self._models.current().stream(
            self._message_manager.to_llm_messages(),
            tools=self._tools.to_schema(),
        ):
            yield event

    async def _set_state(self, state: AssistantState) -> None:
        self._state = state
        await self._event_bus.dispatch(StateChanged(state=state))
