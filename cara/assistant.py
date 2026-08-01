import asyncio
import logging
import threading

from agenttoolkit import Skills
from agenttoolkit.builtins import Workspace
from llmify import ChatModel
from transitbus import EventBus

from cara.agent import Agent
from cara.audio import (
    AudioPlayer,
    Earcon,
    EarconPlayer,
    LocalAudioSink,
    MicrophoneRecorder,
    MicrophoneStream,
    SpeechRecorder,
)
from cara.audio.device import PortAudioDevice
from cara.events import (
    AssistantInterrupted,
    SessionEnded,
    SessionStarted,
)
from cara.listener import SoundListener
from cara.messages import SystemPrompt
from cara.speech import (
    OpenAISpeechToText,
    OpenAITextToSpeech,
    SpeechInput,
    SpeechOutput,
    SpeechSettings,
    SpeechToText,
    TextToSpeech,
)
from cara.tools import Tools, build_tools
from cara.wakeword import WakeWordListener, WakeWordSettings
from cara.wakeword.barge_in import WakeWordBargeIn

logger = logging.getLogger(__name__)

DEFAULT_FOLLOW_UP_TIMEOUT_SECONDS = 7.0


class _ResponseInterrupted(Exception):
    pass


class VoiceAgent:
    def __init__(
        self,
        *,
        llm: ChatModel,
        api_key: str | None = None,
        recorder: SpeechRecorder | None = None,
        player: AudioPlayer | None = None,
        stt: SpeechToText | None = None,
        tts: TextToSpeech | None = None,
        event_bus: EventBus | None = None,
        wake_word_settings: WakeWordSettings,
        tools: Tools | None = None,
        skills: Skills | None = None,
        workspace: Workspace | None = None,
        speech_settings: SpeechSettings | None = None,
        system_prompt: str | SystemPrompt | None = None,
        override_system_prompt: str | None = None,
        extend_system_prompt: str | None = None,
        follow_up_timeout_seconds: float = DEFAULT_FOLLOW_UP_TIMEOUT_SECONDS,
    ) -> None:
        self._audio_device = PortAudioDevice()
        self._microphone = MicrophoneStream(device=self._audio_device)
        self._recorder = recorder or MicrophoneRecorder(self._microphone)
        self._player = player or AudioPlayer(LocalAudioSink(device=self._audio_device))
        configured_tools = build_tools(self._player, skills=skills, workspace=workspace, tools=tools)
        self._speech_settings = speech_settings or SpeechSettings()
        self._wake_word_settings = wake_word_settings
        self._event_bus = event_bus or EventBus()
        self._speech_input = SpeechInput(
            self._recorder,
            stt or OpenAISpeechToText(api_key),
            self._speech_settings,
            self._event_bus,
        )
        self._speech_output = SpeechOutput(
            tts or OpenAITextToSpeech(api_key),
            self._player,
            self._speech_settings,
            self._event_bus,
        )
        self._agent = Agent(
            llm=llm,
            tools=configured_tools,
            skills=skills,
            system_prompt=system_prompt,
            override_system_prompt=override_system_prompt,
            extend_system_prompt=extend_system_prompt,
        )
        self._follow_up_timeout_seconds = follow_up_timeout_seconds
        self._earcons = EarconPlayer(self._player)
        self._sound_listener = SoundListener(self._event_bus, self._earcons)

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

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
        pending_transcript: str | None = None
        ready: threading.Event | None = threading.Event()
        await self._event_bus.dispatch(SessionStarted())
        wake_earcon = asyncio.create_task(self._announce_wake(ready))
        try:
            while True:
                if pending_transcript is not None:
                    transcript = pending_transcript
                    pending_transcript = None
                else:
                    transcript = await self._receive(follow_up=follow_up, ready=ready)
                    ready = None
                if transcript is None:
                    break
                if not transcript:
                    logger.info("Ignoring empty transcription")
                    break

                async with WakeWordBargeIn(wake_word_listener) as barge_in:
                    try:
                        answer = await self._respond(transcript, interrupt=barge_in.interrupt)
                    except _ResponseInterrupted:
                        pending_transcript = await self._receive_barge_in()
                        if pending_transcript is None:
                            break
                        follow_up = False
                        continue
                    if barge_in.interrupt.is_set():
                        pending_transcript = await self._receive_barge_in()
                        if pending_transcript is None:
                            break
                        follow_up = False
                        continue
                    if answer:
                        await self._speech_output.send(answer, cancel=barge_in.interrupt)
                if barge_in.interrupt.is_set():
                    pending_transcript = await self._receive_barge_in()
                    if pending_transcript is None:
                        break
                    follow_up = False
                    continue
                follow_up = True
        finally:
            wake_earcon.cancel()
            await asyncio.gather(wake_earcon, return_exceptions=True)
            await self._event_bus.dispatch(SessionEnded())

    async def _announce_wake(self, ready: threading.Event) -> None:
        try:
            await self._earcons.play(Earcon.WAKE)
        finally:
            ready.set()

    async def _receive_barge_in(self) -> str | None:
        await self._event_bus.dispatch(AssistantInterrupted())
        return await self._speech_input.receive()

    async def _receive(
        self,
        *,
        follow_up: bool = False,
        ready: threading.Event | None = None,
    ) -> str | None:
        initial_silence_timeout = self._follow_up_timeout_seconds if follow_up else None
        return await self._speech_input.receive(
            initial_silence_timeout=initial_silence_timeout,
            ready=ready,
        )

    async def _respond(self, text: str, *, interrupt: asyncio.Event | None = None) -> str:
        if interrupt is None:
            return await self._agent.respond(text)

        response_task = asyncio.create_task(self._agent.respond(text))
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
