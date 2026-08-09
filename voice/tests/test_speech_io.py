import asyncio
import logging
import threading
from collections.abc import Awaitable, Callable

from transitbus import EventBus

from agent.events import AssistantSpeechStarted, UserSpeechEnded, UserSpeechStarted
from voice.audio import AudioOutput, AudioPlayer
from voice.speech import (
    SpeechInput,
    SpeechOutput,
    SpeechSettings,
    SpeechToTextRequest,
    SpeechToTextResponse,
    TextToSpeechRequest,
    TextToSpeechResponse,
)

_ANSWER = "Hallo, wie kann ich helfen?"


class StaticRecorder:
    async def record_until_silence(
        self,
        *,
        initial_silence_timeout: float | None = None,
        ready: threading.Event | None = None,
        on_speech_started: Callable[[], Awaitable[None]] | None = None,
    ) -> bytes | None:
        if on_speech_started is not None:
            await on_speech_started()
        return b"audio"


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


def test_speech_input_records_transcribes_and_emits_lifecycle(caplog) -> None:
    async def run() -> tuple[str | None, list[str]]:
        event_bus = EventBus()
        lifecycle: list[str] = []

        async def capture_started(event: UserSpeechStarted) -> None:
            lifecycle.append("started")

        async def capture_ended(event: UserSpeechEnded) -> None:
            lifecycle.append("ended")

        event_bus.subscribe(capture_started)
        event_bus.subscribe(capture_ended)
        speech_input = SpeechInput(
            StaticRecorder(),
            StaticSpeechToText(),
            SpeechSettings(),
            event_bus,
        )
        return await speech_input.receive(), lifecycle

    with caplog.at_level(logging.INFO, logger="voice.speech.input"):
        transcript, lifecycle = asyncio.run(run())

    assert transcript == "Hallo Welt"
    assert lifecycle == ["started", "ended"]
    assert "[heard] Hallo Welt" in caplog.messages


def test_speech_output_synthesizes_plays_and_emits_lifecycle() -> None:
    async def run() -> tuple[RecordingTextToSpeech, RecordingAudioPlayer, int]:
        event_bus = EventBus()
        player = RecordingAudioPlayer()
        tts = RecordingTextToSpeech()
        speech_output = SpeechOutput(
            tts,
            AudioPlayer(player),
            SpeechSettings(),
            event_bus,
        )
        speech_starts = 0

        async def capture_speech_start(event: AssistantSpeechStarted) -> None:
            nonlocal speech_starts
            speech_starts += 1

        event_bus.subscribe(capture_speech_start)
        await speech_output.send(_ANSWER)
        return tts, player, speech_starts

    tts, player, speech_starts = asyncio.run(run())

    assert tts.texts == [_ANSWER]
    assert player.audio == [_ANSWER.encode()]
    assert speech_starts == 1
