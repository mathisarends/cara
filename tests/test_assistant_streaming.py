import asyncio

from llmify import Function, StreamEnd, StreamTextDelta, StreamToolCall, ToolCall

from cara.assistant import VoiceAssistant
from cara.events import AnswerGenerated, EventBus
from cara.speech import TextToSpeechRequest, TextToSpeechResponse
from cara.wakeword import WakeWordSettings


class UnusedRecorder:
    async def record_until_silence(self, *, initial_silence_timeout: float | None = None) -> bytes | None:
        raise AssertionError("recorder should not be used")


class UnusedSpeechToText:
    async def transcribe(self, request) -> None:
        raise AssertionError("speech-to-text should not be used")


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

    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        self.audio.append(audio)
        if len(self.audio) == 1:
            self.first_playback_started.set()
            await asyncio.wait_for(self.second_delta_generated.wait(), timeout=1)


class CoordinatedChatModel:
    def __init__(self, player: CoordinatedAudioPlayer) -> None:
        self._player = player

    async def stream(self, messages, *, tools):
        yield StreamTextDelta(delta="Erster Satz. ")
        await asyncio.wait_for(self._player.first_playback_started.wait(), timeout=1)
        self._player.second_delta_generated.set()
        yield StreamTextDelta(delta="Zweiter Satz.")
        yield StreamEnd(completion="Erster Satz. Zweiter Satz.")


class EndSessionChatModel:
    async def stream(self, messages, *, tools):
        tool_call = ToolCall(
            id="end-session",
            function=Function(name="end_session", arguments='{"farewell":"Bis bald!"}'),
        )
        yield StreamToolCall(tool_call=tool_call)
        yield StreamEnd(completion="", tool_calls=[tool_call], stop_reason="tool_calls")


def _assistant(*, llm, tts: RecordingTextToSpeech, player: CoordinatedAudioPlayer) -> VoiceAssistant:
    return VoiceAssistant(
        llm=llm,
        recorder=UnusedRecorder(),
        player=player,
        stt=UnusedSpeechToText(),
        tts=tts,
        event_bus=EventBus(),
        wake_word_settings=WakeWordSettings(),
    )


def test_assistant_plays_first_sentence_while_llm_generates_the_rest() -> None:
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

    assert answer == "Erster Satz. Zweiter Satz."
    assert end_session is False
    assert tts.texts == ["Erster Satz.", "Zweiter Satz."]
    assert player.audio == [b"Erster Satz.", b"Zweiter Satz."]
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
