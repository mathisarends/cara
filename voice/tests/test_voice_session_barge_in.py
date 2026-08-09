import asyncio
import threading
from collections.abc import Awaitable, Callable
from pathlib import Path

from llmify import ChatInvokeCompletion, Function, ToolCall, UserMessage
from transitbus import EventBus

from agent.agent import Agent
from agent.events import AssistantInterrupted, UserSpeechEnded, UserSpeechStarted
from agent.tools import build_tools, create_tools
from voice import VoiceSession
from voice.audio import AudioOutput, AudioPlayer, EarconPlayer
from voice.speech import (
    SpeechInput,
    SpeechOutput,
    SpeechSettings,
    SpeechToTextRequest,
    SpeechToTextResponse,
    TextToSpeechRequest,
    TextToSpeechResponse,
)
from voice.wakeword.ports import WakeWordSessionSource


class BargeInRecorder:
    def __init__(self, events: list[str]) -> None:
        self._events = events
        self.recordings = 0

    async def record_until_silence(
        self,
        *,
        initial_silence_timeout: float | None = None,
        ready: threading.Event | None = None,
        on_speech_started: Callable[[], Awaitable[None]] | None = None,
    ) -> bytes | None:
        while ready is not None and not ready.is_set():
            await asyncio.sleep(0)
        self._events.append("record")
        if self.recordings >= 2:
            return None
        self.recordings += 1
        if on_speech_started is not None:
            await on_speech_started()
        return b"initial request" if self.recordings == 1 else b"corrected request"


class RepeatedWakeWordListener(WakeWordSessionSource):
    def __init__(self, tool_started: asyncio.Event) -> None:
        self._tool_started = tool_started
        self.detection_calls = 0

    async def detections(self):
        yield 0.9

    async def detect_once(self, *, cancel: asyncio.Event | None = None) -> float | None:
        self.detection_calls += 1
        if self.detection_calls == 1:
            await self._tool_started.wait()
            return 0.9

        assert cancel is not None
        await cancel.wait()
        return None


class MappingSpeechToText:
    def __init__(self) -> None:
        self.audio: list[bytes] = []

    async def transcribe(self, request: SpeechToTextRequest) -> SpeechToTextResponse:
        assert request.audio is not None
        self.audio.append(request.audio)
        return SpeechToTextResponse(
            text=request.audio.decode(),
            model=request.model,
            response_format=request.response_format,
            raw={},
        )


class ImmediateTextToSpeech:
    async def synthesize(self, request: TextToSpeechRequest) -> TextToSpeechResponse:
        return TextToSpeechResponse(
            audio=request.text.encode(),
            model=request.model,
            voice=request.voice,
            response_format=request.response_format,
            content_type="audio/wav",
        )


class ImmediateAudioPlayer:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    @property
    def output(self) -> AudioOutput:
        return AudioOutput.LOCAL

    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        self._events.append("play")


class TwoTurnChatModel:
    def __init__(self) -> None:
        self.calls = 0
        self.messages: list[list[object]] = []

    async def invoke(self, messages, *, tools):
        self.calls += 1
        self.messages.append(messages)
        if self.calls == 1:
            tool_call = ToolCall(
                id="slow-tool",
                function=Function(name="slow_tool", arguments="{}"),
            )
            return ChatInvokeCompletion(
                completion="", tool_calls=[tool_call], stop_reason="tool_calls"
            )

        return ChatInvokeCompletion(completion="Erledigt.")


def test_repeated_wake_word_interrupts_tool_and_starts_next_turn(
    tmp_path: Path,
) -> None:
    async def run() -> tuple[
        BargeInRecorder,
        RepeatedWakeWordListener,
        MappingSpeechToText,
        TwoTurnChatModel,
        list[AssistantInterrupted],
        list[str],
        bool,
        list[str],
    ]:
        tool_started = asyncio.Event()
        tool_cancelled = asyncio.Event()
        tools = create_tools()

        @tools.action("Wait until released.", name="slow_tool")
        async def slow_tool() -> None:
            tool_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                tool_cancelled.set()

        events: list[str] = []
        recorder = BargeInRecorder(events)
        wake_word_listener = RepeatedWakeWordListener(tool_started)
        stt = MappingSpeechToText()
        llm = TwoTurnChatModel()
        event_bus = EventBus()
        interruptions: list[AssistantInterrupted] = []
        speech_lifecycle: list[str] = []

        async def capture_interruption(event: AssistantInterrupted) -> None:
            interruptions.append(event)

        async def capture_speech_started(event: UserSpeechStarted) -> None:
            speech_lifecycle.append("started")

        async def capture_speech_ended(event: UserSpeechEnded) -> None:
            speech_lifecycle.append("ended")

        event_bus.subscribe(capture_interruption)
        event_bus.subscribe(capture_speech_started)
        event_bus.subscribe(capture_speech_ended)
        player = AudioPlayer(ImmediateAudioPlayer(events))
        speech_settings = SpeechSettings()
        session = VoiceSession(
            agent=Agent(
                llm=llm,
                tools=build_tools(player, tools=tools),
                prompt_root=tmp_path,
            ),
            speech_input=SpeechInput(
                recorder,
                stt,
                speech_settings,
                event_bus,
            ),
            speech_output=SpeechOutput(
                ImmediateTextToSpeech(),
                player,
                speech_settings,
                event_bus,
            ),
            wake_word_listener=wake_word_listener,
            event_bus=event_bus,
            earcons=EarconPlayer(player),
        )

        await asyncio.wait_for(session.run_once(), timeout=2)
        return (
            recorder,
            wake_word_listener,
            stt,
            llm,
            interruptions,
            speech_lifecycle,
            tool_cancelled.is_set(),
            events,
        )

    (
        recorder,
        wake_word_listener,
        stt,
        llm,
        interruptions,
        speech_lifecycle,
        tool_cancelled,
        events,
    ) = asyncio.run(run())

    assert recorder.recordings == 2
    assert wake_word_listener.detection_calls == 2
    assert stt.audio == [b"initial request", b"corrected request"]
    assert tool_cancelled is True
    assert events[:4] == ["play", "record", "play", "record"]
    assert len(interruptions) == 1
    assert speech_lifecycle == ["started", "ended", "started", "ended"]
    assert [
        message.content
        for message in llm.messages[1]
        if isinstance(message, UserMessage)
    ] == [
        "initial request",
        "corrected request",
    ]
