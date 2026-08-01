import asyncio
import logging
import threading
from collections.abc import Awaitable, Callable
from pathlib import Path

from agenttoolkit import Skills
from agenttoolkit.builtins import LocalWorkspace
from llmify import AssistantMessage, ChatInvokeCompletion, Function, ToolCall, ToolResultMessage
from transitbus import EventBus

from cara.assistant import VoiceAgent
from cara.audio import AudioOutput, AudioPlayer
from cara.events import AssistantSpeechStarted
from cara.speech import SpeechToTextRequest, SpeechToTextResponse, TextToSpeechRequest, TextToSpeechResponse
from cara.tools import ActionResult, create_tools
from cara.tools.params import WeatherParams
from cara.wakeword import WakeWordSettings

_ANSWER = "Hallo, wie kann ich helfen?"


def _skills(root: Path) -> Skills:
    directory = root / "weather"
    directory.mkdir()
    (directory / "SKILL.md").write_text(
        "---\nname: weather\ndescription: Wetter abrufen.\n---\nRufe weather_lookup auf.\n",
        encoding="utf-8",
    )
    return Skills.from_local_dir(root)


class UnusedRecorder:
    async def record_until_silence(
        self,
        *,
        initial_silence_timeout: float | None = None,
        ready: threading.Event | None = None,
        on_speech_started: Callable[[], Awaitable[None]] | None = None,
    ) -> bytes | None:
        raise AssertionError("recorder should not be used")


class UnusedSpeechToText:
    async def transcribe(self, request) -> None:
        raise AssertionError("speech-to-text should not be used")


class StaticSpeechToText:
    async def transcribe(self, request: SpeechToTextRequest) -> SpeechToTextResponse:
        return SpeechToTextResponse(
            text=" Hallo Welt ",
            model=request.model,
            response_format=request.response_format,
            raw={},
        )


class RecordingTextToSpeech:
    def __init__(self) -> None:
        self.texts: list[str] = []

    async def synthesize(self, request: TextToSpeechRequest) -> TextToSpeechResponse:
        self.texts.append(request.text)
        return TextToSpeechResponse(
            audio=request.text.encode(),
            model=request.model,
            voice=request.voice,
            response_format=request.response_format,
            content_type="audio/wav",
        )


class RecordingAudioPlayer:
    def __init__(self) -> None:
        self.audio: list[bytes] = []

    @property
    def output(self) -> AudioOutput:
        return AudioOutput.LOCAL

    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        self.audio.append(audio)


class StaticChatModel:
    async def invoke(self, messages, *, tools):
        return ChatInvokeCompletion(completion=_ANSWER)


class MultiRoundToolChatModel:
    def __init__(self) -> None:
        self.messages: list[list[object]] = []

    async def invoke(self, messages, *, tools):
        self.messages.append(messages)
        if len(self.messages) == 1:
            tool_call = ToolCall(
                id="load-weather-skill",
                function=Function(
                    name="load_skill",
                    arguments='{"name":"weather"}',
                ),
            )
            return ChatInvokeCompletion(completion="", tool_calls=[tool_call], stop_reason="tool_calls")
        if len(self.messages) == 2:
            tool_call = ToolCall(
                id="fetch-weather",
                function=Function(
                    name="weather_lookup",
                    arguments="{}",
                ),
            )
            return ChatInvokeCompletion(completion="", tool_calls=[tool_call], stop_reason="tool_calls")

        return ChatInvokeCompletion(completion="Heute sind es 22 Grad und es ist sonnig.")


class DeniedPathChatModel:
    def __init__(self) -> None:
        self.messages: list[list[object]] = []

    async def invoke(self, messages, *, tools):
        self.messages.append(messages)
        if len(self.messages) == 1:
            tool_call = ToolCall(
                id="write-outside-workspace",
                function=Function(
                    name="write_file",
                    arguments=('{"path":"../outside.txt","content":"unsafe"}'),
                ),
            )
            return ChatInvokeCompletion(completion="", tool_calls=[tool_call], stop_reason="tool_calls")

        return ChatInvokeCompletion(completion="Ich kann nur innerhalb des Arbeitsbereichs schreiben.")


def _assistant(*, llm, tts: RecordingTextToSpeech, player: RecordingAudioPlayer, stt=None) -> VoiceAgent:
    return VoiceAgent(
        llm=llm,
        recorder=UnusedRecorder(),
        player=AudioPlayer(player),
        stt=stt or UnusedSpeechToText(),
        tts=tts,
        event_bus=EventBus(),
        wake_word_settings=WakeWordSettings(),
    )


def test_assistant_logs_transcript_directly(caplog) -> None:
    player = RecordingAudioPlayer()
    tts = RecordingTextToSpeech()
    assistant = _assistant(
        llm=StaticChatModel(),
        tts=tts,
        player=player,
        stt=StaticSpeechToText(),
    )

    with caplog.at_level(logging.INFO, logger="cara.assistant"):
        transcript = asyncio.run(assistant._transcribe(b"audio"))

    assert transcript == "Hallo Welt"
    assert "[heard] Hallo Welt" in caplog.messages


def test_assistant_generates_full_answer_then_speaks_it_once() -> None:
    async def run() -> tuple[str, RecordingTextToSpeech, RecordingAudioPlayer, int]:
        player = RecordingAudioPlayer()
        tts = RecordingTextToSpeech()
        assistant = _assistant(llm=StaticChatModel(), tts=tts, player=player)
        speech_starts = 0

        async def capture_speech_start(event: AssistantSpeechStarted) -> None:
            nonlocal speech_starts
            speech_starts += 1

        assistant.event_bus.subscribe(capture_speech_start)
        answer = await asyncio.wait_for(assistant._think(), timeout=2)
        await assistant._speak(answer)
        return answer, tts, player, speech_starts

    answer, tts, player, speech_starts = asyncio.run(run())

    assert answer == _ANSWER
    assert tts.texts == [_ANSWER]
    assert player.audio == [_ANSWER.encode()]
    assert speech_starts == 1


def test_assistant_continues_after_each_tool_round_until_final_answer(tmp_path: Path) -> None:
    async def run() -> tuple[str, MultiRoundToolChatModel, RecordingTextToSpeech]:
        player = RecordingAudioPlayer()
        tts = RecordingTextToSpeech()
        llm = MultiRoundToolChatModel()
        tools = create_tools()

        @tools.action("Wetter abrufen.", name="weather_lookup", params=WeatherParams)
        async def weather_lookup(params: WeatherParams) -> ActionResult:
            return ActionResult.success("22 Grad und sonnig.")

        skills = _skills(tmp_path)
        assistant = VoiceAgent(
            llm=llm,
            recorder=UnusedRecorder(),
            player=AudioPlayer(player),
            stt=UnusedSpeechToText(),
            tts=tts,
            event_bus=EventBus(),
            wake_word_settings=WakeWordSettings(),
            tools=tools,
            skills=skills,
        )
        answer = await assistant._think()
        return answer, llm, tts

    answer, llm, tts = asyncio.run(run())

    assert answer == "Heute sind es 22 Grad und es ist sonnig."
    assert len(llm.messages) == 3

    second_round_results = [message for message in llm.messages[1] if isinstance(message, ToolResultMessage)]
    assert [(result.tool_call_id, result.content) for result in second_round_results] == [
        ("load-weather-skill", "Rufe weather_lookup auf.")
    ]
    third_round_calls = [message for message in llm.messages[2] if isinstance(message, AssistantMessage)]
    third_round_results = [message for message in llm.messages[2] if isinstance(message, ToolResultMessage)]
    assert [call.tool_calls[0].id for call in third_round_calls if call.tool_calls] == [
        "load-weather-skill",
        "fetch-weather",
    ]
    assert [(result.tool_call_id, result.content) for result in third_round_results] == [
        ("load-weather-skill", "Rufe weather_lookup auf."),
        ("fetch-weather", "22 Grad und sonnig."),
    ]


def test_tool_error_is_sent_to_the_model_as_a_tool_result(tmp_path: Path) -> None:
    async def run() -> DeniedPathChatModel:
        player = RecordingAudioPlayer()
        llm = DeniedPathChatModel()
        assistant = VoiceAgent(
            llm=llm,
            recorder=UnusedRecorder(),
            player=AudioPlayer(player),
            stt=UnusedSpeechToText(),
            tts=RecordingTextToSpeech(),
            event_bus=EventBus(),
            wake_word_settings=WakeWordSettings(),
            tools=create_tools(),
            workspace=LocalWorkspace(tmp_path),
        )

        await assistant._think()
        return llm

    llm = asyncio.run(run())

    tool_results = [message for message in llm.messages[1] if isinstance(message, ToolResultMessage)]
    assert len(tool_results) == 1
    assert tool_results[0].tool_call_id == "write-outside-workspace"
    assert tool_results[0].content == "Internal tool error."
