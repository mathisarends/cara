import asyncio
import threading

from llmify import Function, StreamEnd, StreamToolCall, ToolCall, UserMessage

from cara.assistant import VoiceAssistant
from cara.audio import AudioOutput, AudioPlayer
from cara.events import AssistantState, EventBus, Interrupted
from cara.speech import (
    SpeechToTextRequest,
    SpeechToTextResponse,
    TextToSpeechRequest,
    TextToSpeechResponse,
)
from cara.tools import ActionResult, Tools
from cara.wakeword import WakeWordSettings
from cara.wakeword.ports import WakeWordDetectionSource


class BargeInRecorder:
    def __init__(self, events: list[str]) -> None:
        self._events = events
        self.recordings = 0

    async def record_until_silence(
        self,
        *,
        initial_silence_timeout: float | None = None,
        ready: threading.Event | None = None,
    ) -> bytes | None:
        while ready is not None and not ready.is_set():
            await asyncio.sleep(0)
        self.recordings += 1
        self._events.append("record")
        return b"initial request" if self.recordings == 1 else b"corrected request"


class RepeatedWakeWordListener(WakeWordDetectionSource):
    def __init__(self, tool_started: asyncio.Event) -> None:
        self._tool_started = tool_started
        self.detections = 0

    async def detect_once(self, *, cancel: asyncio.Event | None = None) -> float | None:
        self.detections += 1
        if self.detections == 1:
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

    async def stream(self, messages, *, tools):
        self.calls += 1
        self.messages.append(messages)
        if self.calls == 1:
            tool_call = ToolCall(
                id="slow-tool",
                function=Function(name="slow_tool", arguments="{}"),
            )
        else:
            tool_call = ToolCall(
                id="end-session",
                function=Function(
                    name="end_session",
                    arguments='{"farewell":"Erledigt.","status":"Ich beende die Sitzung."}',
                ),
            )
        yield StreamToolCall(tool_call=tool_call)
        yield StreamEnd(completion="", tool_calls=[tool_call], stop_reason="tool_calls")


def test_repeated_wake_word_interrupts_tool_and_starts_next_turn() -> None:
    async def run() -> tuple[
        BargeInRecorder,
        RepeatedWakeWordListener,
        MappingSpeechToText,
        TwoTurnChatModel,
        list[Interrupted],
        bool,
        list[str],
    ]:
        tool_started = asyncio.Event()
        tool_cancelled = asyncio.Event()
        tools = Tools()

        @tools.action(name="slow_tool")
        async def slow_tool() -> ActionResult:
            tool_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                tool_cancelled.set()
            return ActionResult.success()

        events: list[str] = []
        recorder = BargeInRecorder(events)
        wake_word_listener = RepeatedWakeWordListener(tool_started)
        stt = MappingSpeechToText()
        llm = TwoTurnChatModel()
        event_bus = EventBus()
        interruptions: list[Interrupted] = []

        async def capture_interruption(event: Interrupted) -> None:
            interruptions.append(event)

        event_bus.subscribe(Interrupted, capture_interruption)
        assistant = VoiceAssistant(
            llm=llm,
            recorder=recorder,
            player=AudioPlayer(ImmediateAudioPlayer(events)),
            stt=stt,
            tts=ImmediateTextToSpeech(),
            event_bus=event_bus,
            wake_word_settings=WakeWordSettings(),
            tools=tools,
        )

        await asyncio.wait_for(assistant._run(wake_word_listener), timeout=2)
        return recorder, wake_word_listener, stt, llm, interruptions, tool_cancelled.is_set(), events

    recorder, wake_word_listener, stt, llm, interruptions, tool_cancelled, events = asyncio.run(run())

    assert recorder.recordings == 2
    assert wake_word_listener.detections == 2
    assert stt.audio == [b"initial request", b"corrected request"]
    assert tool_cancelled is True
    assert events[:4] == ["play", "record", "play", "record"]
    assert [event.phase for event in interruptions] == [AssistantState.CALLING_TOOL]
    assert [message.content for message in llm.messages[1] if isinstance(message, UserMessage)] == [
        "initial request",
        "corrected request",
    ]
