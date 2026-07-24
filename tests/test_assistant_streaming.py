import asyncio
import logging
from pathlib import Path

from llmify import AssistantMessage, Function, StreamEnd, StreamTextDelta, StreamToolCall, ToolCall, ToolResultMessage

from cara.assistant import VoiceAssistant
from cara.audio import AudioOutput, AudioPlayer
from cara.events import AnswerGenerated, EventBus
from cara.file_system import Workspace
from cara.skills import Skill, Skills
from cara.speech import SpeechToTextRequest, SpeechToTextResponse, TextToSpeechRequest, TextToSpeechResponse
from cara.tools import ActionResult, Tools
from cara.tools.params import WeatherParams
from cara.wakeword import WakeWordSettings

_FIRST_SENTENCE = f"{'A' * 339}."
_SECOND_SENTENCE = f"{'B' * 139}."
_THIRD_SENTENCE = f"{'C' * 319}."
_FIRST_SPEECH_CHUNK = f"{_FIRST_SENTENCE} {_SECOND_SENTENCE}"
_FINAL_SPEECH_CHUNK = f"{_THIRD_SENTENCE} Abschluss."
_STREAMED_ANSWER = f"{_FIRST_SPEECH_CHUNK} {_FINAL_SPEECH_CHUNK}"


class UnusedRecorder:
    async def record_until_silence(self, *, initial_silence_timeout: float | None = None) -> bytes | None:
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


class CoordinatedAudioPlayer:
    def __init__(self) -> None:
        self.audio: list[bytes] = []
        self.first_playback_started = asyncio.Event()
        self.second_delta_generated = asyncio.Event()

    @property
    def output(self) -> AudioOutput:
        return AudioOutput.LOCAL

    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        self.audio.append(audio)
        if len(self.audio) == 1:
            self.first_playback_started.set()
            await asyncio.wait_for(self.second_delta_generated.wait(), timeout=1)


class CoordinatedChatModel:
    def __init__(self, player: CoordinatedAudioPlayer) -> None:
        self._player = player

    async def stream(self, messages, *, tools):
        yield StreamTextDelta(delta=f"{_FIRST_SPEECH_CHUNK} {_THIRD_SENTENCE}")
        await asyncio.wait_for(self._player.first_playback_started.wait(), timeout=1)
        self._player.second_delta_generated.set()
        yield StreamTextDelta(delta=" Abschluss.")
        yield StreamEnd(completion=_STREAMED_ANSWER)


class EndSessionChatModel:
    async def stream(self, messages, *, tools):
        tool_call = ToolCall(
            id="end-session",
            function=Function(
                name="end_session",
                arguments='{"farewell":"Bis bald!"}',
            ),
        )
        yield StreamToolCall(tool_call=tool_call)
        yield StreamEnd(completion="", tool_calls=[tool_call], stop_reason="tool_calls")


class MultiRoundToolChatModel:
    def __init__(self) -> None:
        self.messages: list[list[object]] = []

    async def stream(self, messages, *, tools):
        self.messages.append(messages)
        if len(self.messages) == 1:
            tool_call = ToolCall(
                id="load-weather-skill",
                function=Function(
                    name="load_skill",
                    arguments='{"name":"weather"}',
                ),
            )
            yield StreamToolCall(tool_call=tool_call)
            yield StreamEnd(completion="", tool_calls=[tool_call], stop_reason="tool_calls")
            return
        if len(self.messages) == 2:
            tool_call = ToolCall(
                id="fetch-weather",
                function=Function(
                    name="weather_lookup",
                    arguments="{}",
                ),
            )
            yield StreamToolCall(tool_call=tool_call)
            yield StreamEnd(completion="", tool_calls=[tool_call], stop_reason="tool_calls")
            return

        answer = "Heute sind es 22 Grad und es ist sonnig."
        yield StreamTextDelta(delta=answer)
        yield StreamEnd(completion=answer)


class DeniedPathChatModel:
    def __init__(self) -> None:
        self.messages: list[list[object]] = []

    async def stream(self, messages, *, tools):
        self.messages.append(messages)
        if len(self.messages) == 1:
            tool_call = ToolCall(
                id="write-outside-workspace",
                function=Function(
                    name="write_file",
                    arguments=('{"path":"../outside.txt","content":"unsafe"}'),
                ),
            )
            yield StreamToolCall(tool_call=tool_call)
            yield StreamEnd(completion="", tool_calls=[tool_call], stop_reason="tool_calls")
            return

        answer = "Ich kann nur innerhalb des Arbeitsbereichs schreiben."
        yield StreamTextDelta(delta=answer)
        yield StreamEnd(completion=answer)


def _assistant(*, llm, tts: RecordingTextToSpeech, player: CoordinatedAudioPlayer, stt=None) -> VoiceAssistant:
    return VoiceAssistant(
        llm=llm,
        recorder=UnusedRecorder(),
        player=AudioPlayer(player),
        stt=stt or UnusedSpeechToText(),
        tts=tts,
        event_bus=EventBus(),
        wake_word_settings=WakeWordSettings(),
    )


def test_assistant_logs_transcript_without_event_subscribers(caplog) -> None:
    player = CoordinatedAudioPlayer()
    tts = RecordingTextToSpeech()
    assistant = _assistant(
        llm=CoordinatedChatModel(player),
        tts=tts,
        player=player,
        stt=StaticSpeechToText(),
    )

    with caplog.at_level(logging.INFO, logger="cara.assistant"):
        transcript = asyncio.run(assistant._transcribe(b"audio"))

    assert transcript == "Hallo Welt"
    assert "\x1b[96m[heard] Hallo Welt\x1b[0m" in caplog.messages


def test_assistant_plays_first_natural_chunk_while_llm_generates_the_rest() -> None:
    async def run() -> tuple[str, bool, RecordingTextToSpeech, CoordinatedAudioPlayer, list[str]]:
        player = CoordinatedAudioPlayer()
        tts = RecordingTextToSpeech()
        assistant = _assistant(llm=CoordinatedChatModel(player), tts=tts, player=player)
        answers: list[str] = []

        async def capture_answer(event: AnswerGenerated) -> None:
            answers.append(event.answer)

        assistant.event_bus.subscribe(capture_answer)
        answer, end_session = await asyncio.wait_for(assistant._think(), timeout=2)
        return answer, end_session, tts, player, answers

    answer, end_session, tts, player, answers = asyncio.run(run())

    assert answer == _STREAMED_ANSWER
    assert end_session is False
    assert tts.texts == [_FIRST_SPEECH_CHUNK, _FINAL_SPEECH_CHUNK]
    assert player.audio == [_FIRST_SPEECH_CHUNK.encode(), _FINAL_SPEECH_CHUNK.encode()]
    assert answers == [answer]


def test_assistant_continues_after_each_tool_round_until_final_answer() -> None:
    async def run() -> tuple[str, MultiRoundToolChatModel, RecordingTextToSpeech, list[str]]:
        player = CoordinatedAudioPlayer()
        player.second_delta_generated.set()
        tts = RecordingTextToSpeech()
        llm = MultiRoundToolChatModel()
        tools = Tools()

        @tools.action(name="weather_lookup", params=WeatherParams)
        async def weather_lookup(params: WeatherParams) -> ActionResult:
            return ActionResult.success("22 Grad und sonnig.")

        skills = Skills([Skill(name="weather", description="Wetter abrufen.", instructions="Rufe weather_lookup auf.")])
        assistant = VoiceAssistant(
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
        answers: list[str] = []

        async def capture_answer(event: AnswerGenerated) -> None:
            answers.append(event.answer)

        assistant.event_bus.subscribe(capture_answer)
        answer, end_session = await assistant._think()
        assert end_session is False
        return answer, llm, tts, answers

    answer, llm, tts, answers = asyncio.run(run())

    assert answer == "Heute sind es 22 Grad und es ist sonnig."
    assert len(llm.messages) == 3
    assert tts.texts == [answer]
    assert answers == [answer]

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


def test_path_policy_denial_is_sent_to_the_model_as_a_tool_result(tmp_path: Path) -> None:
    async def run() -> DeniedPathChatModel:
        player = CoordinatedAudioPlayer()
        player.second_delta_generated.set()
        llm = DeniedPathChatModel()
        assistant = VoiceAssistant(
            llm=llm,
            recorder=UnusedRecorder(),
            player=AudioPlayer(player),
            stt=UnusedSpeechToText(),
            tts=RecordingTextToSpeech(),
            event_bus=EventBus(),
            wake_word_settings=WakeWordSettings(),
            tools=Tools(workspace=Workspace(tmp_path)),
        )

        await assistant._think()
        return llm

    llm = asyncio.run(run())

    tool_results = [message for message in llm.messages[1] if isinstance(message, ToolResultMessage)]
    assert [(result.tool_call_id, result.content) for result in tool_results] == [
        (
            "write-outside-workspace",
            "Path '../outside.txt' is outside the workspace. Use a relative path below the workspace root.",
        )
    ]


def test_assistant_speaks_end_session_tool_result() -> None:
    async def run() -> tuple[str, bool, RecordingTextToSpeech, CoordinatedAudioPlayer]:
        player = CoordinatedAudioPlayer()
        player.second_delta_generated.set()
        tts = RecordingTextToSpeech()
        assistant = _assistant(llm=EndSessionChatModel(), tts=tts, player=player)
        answer, end_session = await asyncio.wait_for(assistant._think(), timeout=2)
        return answer, end_session, tts, player

    answer, end_session, tts, player = asyncio.run(run())

    assert answer == "Bis bald!"
    assert end_session is True
    assert tts.texts == ["Bis bald!"]
    assert player.audio == [b"Bis bald!"]
