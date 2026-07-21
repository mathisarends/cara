import asyncio
import logging

from llmify import Function, StreamEnd, StreamTextDelta, StreamToolCall, ToolCall

from cara.assistant import VoiceAssistant
from cara.audio import AudioOutput, AudioPlayer
from cara.events import AnswerGenerated, EventBus
from cara.speech import SpeechToTextRequest, SpeechToTextResponse, TextToSpeechRequest, TextToSpeechResponse
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
                arguments='{"farewell":"Bis bald!","status":"Ich beende die Sitzung..."}',
            ),
        )
        yield StreamToolCall(tool_call=tool_call)
        yield StreamEnd(completion="", tool_calls=[tool_call], stop_reason="tool_calls")


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

        assistant.event_bus.subscribe(AnswerGenerated, capture_answer)
        answer, end_session = await asyncio.wait_for(assistant._think(), timeout=2)
        return answer, end_session, tts, player, answers

    answer, end_session, tts, player, answers = asyncio.run(run())

    assert answer == _STREAMED_ANSWER
    assert end_session is False
    assert tts.texts == [_FIRST_SPEECH_CHUNK, _FINAL_SPEECH_CHUNK]
    assert player.audio == [_FIRST_SPEECH_CHUNK.encode(), _FINAL_SPEECH_CHUNK.encode()]
    assert answers == [answer]


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
