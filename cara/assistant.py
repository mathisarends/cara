import asyncio
import json
import logging
from collections.abc import AsyncIterator

from llmify import ChatInvokeCompletion, ChatModel, ChatOpenAI, StreamEvent, ToolCall

from cara.audio import (
    AudioOutputStrategy,
    AudioPlayer,
    Earcon,
    EarconPlayer,
    MicrophoneRecorder,
    SpeechRecorder,
    WavAudioPlayer,
    WebRtcEchoCanceller,
)
from cara.audio.barge_in import BargeInCapture
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
from cara.messages import MessageManager, SystemPrompt
from cara.replies import StreamingReply
from cara.skills import SkillRepository
from cara.speech import (
    OpenAISpeechToText,
    OpenAITextToSpeech,
    SpeechToText,
    SpeechToTextRequest,
    TextToSpeech,
)
from cara.speech.streaming import NaturalPauseChunker, StreamingTextToSpeech
from cara.tools import ActionKind, Tools
from cara.views import SpeechSettings
from cara.wakeword import WakeWordListener, WakeWordSettings

logger = logging.getLogger(__name__)

DEFAULT_FOLLOW_UP_TIMEOUT_SECONDS = 7.0


class _ResponseInterrupted(Exception):
    pass


class VoiceAssistant:
    def __init__(
        self,
        *,
        llm: ChatModel | None = None,
        api_key: str | None = None,
        recorder: SpeechRecorder | None = None,
        player: AudioOutputStrategy | None = None,
        stt: SpeechToText | None = None,
        tts: TextToSpeech | None = None,
        event_bus: EventBus | None = None,
        wake_word_settings: WakeWordSettings,
        tools: Tools | None = None,
        skills: SkillRepository | None = None,
        file_system: FileSystem | None = None,
        speech_settings: SpeechSettings | None = None,
        system_prompt: str | SystemPrompt | None = None,
        override_system_prompt: str | None = None,
        extend_system_prompt: str | None = None,
        follow_up_timeout_seconds: float = DEFAULT_FOLLOW_UP_TIMEOUT_SECONDS,
    ) -> None:
        self._llm = llm or ChatOpenAI(model="gpt-5.6-terra")
        if recorder is None and player is None:
            echo_canceller = WebRtcEchoCanceller()
            recorder = MicrophoneRecorder(echo_canceller=echo_canceller)
            player = WavAudioPlayer(echo_canceller=echo_canceller)

        self._recorder = recorder or MicrophoneRecorder()
        output = player or WavAudioPlayer()
        self._player = output if isinstance(output, AudioPlayer) else AudioPlayer({"local": output})
        self._stt = stt or OpenAISpeechToText(api_key)
        tts = tts or OpenAITextToSpeech(api_key)
        self._tools = tools or Tools()
        self._tools.provide(self._player)
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
        self._pending_skill_results: list[tuple[ToolCall, str]] = []

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
            wake_word=self._wake_word_settings.wake_word,
            sensitivity=self._wake_word_settings.sensitivity,
        )
        try:
            async for _ in listener.detections():
                await self._run(listener)
        finally:
            listener.close()

    async def _run(self, wake_word_listener: WakeWordListener) -> None:
        follow_up = False
        pending_audio: bytes | None = None
        await self._event_bus.dispatch(SessionStarted())
        await self._earcons.play(Earcon.WAKE)
        try:
            while True:
                await self._event_bus.dispatch(TurnStarted())
                self._pending_skill_results = []

                audio = pending_audio
                pending_audio = None
                if audio is None:
                    audio = await self._record(follow_up=follow_up)
                if audio is None:
                    break
                transcript = await self._transcribe(audio)
                if not transcript:
                    logger.info("Ignoring empty transcription")
                    break

                self._message_manager.add_user(transcript)
                async with BargeInCapture(wake_word_listener) as barge_in:
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
                for tool_call, content in self._pending_skill_results:
                    self._message_manager.add_tool_result(tool_call, content)
                self._message_manager.add_assistant(answer)

                if end_session:
                    break
                follow_up = True
        finally:
            await self._event_bus.dispatch(SessionEnded())
            await self._set_state(AssistantState.IDLE)

    async def _receive_barge_in(
        self,
        *,
        phase: AssistantState,
    ) -> bytes | None:
        await self._event_bus.dispatch(Interrupted(phase=phase))
        return await self._record()

    async def _record(self, *, follow_up: bool = False) -> bytes | None:
        if follow_up:
            await self._set_state(AssistantState.WAITING_FOLLOW_UP)
            return await self._recorder.record_until_silence(
                initial_silence_timeout=self._follow_up_timeout_seconds,
            )
        await self._set_state(AssistantState.LISTENING)
        return await self._recorder.record_until_silence()

    async def _transcribe(self, audio: bytes) -> str:
        await self._set_state(AssistantState.TRANSCRIBING)
        response = await self._stt.transcribe(SpeechToTextRequest(audio=audio, language=self._speech_settings.language))
        transcript = response.text.strip()
        if transcript:
            logger.info("User said: %s", transcript)
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
        return reply_task.result()

    async def _resolve_streaming_reply(self, reply: StreamingReply) -> tuple[str, bool]:
        try:
            completion = await reply.collect()
            answer, end_session = await self._resolve_completion(completion, reply)
            logger.info("Assistant answer: %s", answer)
            await self._event_bus.dispatch(AnswerGenerated(answer=answer))
            reply.finish(answer)
            return answer, end_session
        finally:
            reply.close()

    async def _resolve_completion(
        self,
        completion: ChatInvokeCompletion[str],
        reply: StreamingReply,
    ) -> tuple[str, bool]:
        answer = completion.completion.strip()
        end_session = False
        for tool_call in completion.tool_calls:
            name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments or "{}")
            tool = self._tools.get(name)
            status = tool.status(arguments) if tool is not None else None

            await self._set_state(AssistantState.CALLING_TOOL)
            if status and tool is not None and tool.kind is ActionKind.GENERIC:
                reply.announce(status)

            result = await self._tools.execute(name, arguments)
            if tool is not None and tool.kind is ActionKind.END_SESSION:
                end_session = True
                if result.content:
                    answer = result.content.strip()
            elif name == "load_skill" and result.ok and result.content:
                self._pending_skill_results.append((tool_call, result.content))
        return answer, end_session

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
        async for event in self._llm.stream(
            self._message_manager.to_llm_messages(),
            tools=self._tools.to_schema(),
        ):
            yield event

    async def _set_state(self, state: AssistantState) -> None:
        self._state = state
        await self._event_bus.dispatch(StateChanged(state=state))
