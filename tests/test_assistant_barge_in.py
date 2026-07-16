import asyncio

from llmify import Function, StreamEnd, StreamToolCall, ToolCall, UserMessage

from cara.assistant import VoiceAssistant
from cara.events import AssistantState, EventBus, Interrupted
from cara.speech import (
    SpeechToTextRequest,
    SpeechToTextResponse,
    TextToSpeechRequest,
    TextToSpeechResponse,
)
from cara.tools import ActionResult, Tools
from cara.wakeword import WakeWordSettings


class BargeInRecorder:
    def __init__(self, tool_started: asyncio.Event) -> None:
        self._tool_started = tool_started
        self.regular_recordings = 0
        self.background_recordings = 0

    async def record_until_silence(
        self,
        *,
        initial_silence_timeout: float | None = None,
        speech_started: asyncio.Event | None = None,
        cancel: asyncio.Event | None = None,
    ) -> bytes | None:
        if speech_started is None:
            self.regular_recordings += 1
            return b"initial request"

        self.background_recordings += 1
        if self.background_recordings == 1:
            await self._tool_started.wait()
            speech_started.set()
            return b"corrected request"

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
    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        pass


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


def test_user_speech_interrupts_tool_and_becomes_next_turn() -> None:
    async def run() -> tuple[BargeInRecorder, MappingSpeechToText, TwoTurnChatModel, list[Interrupted], bool]:
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

        recorder = BargeInRecorder(tool_started)
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
            player=ImmediateAudioPlayer(),
            stt=stt,
            tts=ImmediateTextToSpeech(),
            event_bus=event_bus,
            wake_word_settings=WakeWordSettings(),
            tools=tools,
        )

        await asyncio.wait_for(assistant._run(), timeout=2)
        return recorder, stt, llm, interruptions, tool_cancelled.is_set()

    recorder, stt, llm, interruptions, tool_cancelled = asyncio.run(run())

    assert recorder.regular_recordings == 1
    assert recorder.background_recordings == 2
    assert stt.audio == [b"initial request", b"corrected request"]
    assert tool_cancelled is True
    assert [event.phase for event in interruptions] == [AssistantState.CALLING_TOOL]
    assert [message.content for message in llm.messages[1] if isinstance(message, UserMessage)] == [
        "initial request",
        "corrected request",
    ]
