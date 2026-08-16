from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, AsyncIterator

from transitbus import EventBus

from voice.audio import AudioHub, AudioInput, AudioOutput, PlaybackCoordinator
from voice.pipeline import TurnController, TurnState
from voice.stt import SpeechToText, Transcription, TranscriptionKind
from voice.tts import TextToSpeech
from voice.wakeword import WakeWordDetection, WakeWordSource


class _Input(AudioInput):
    def __init__(self) -> None:
        self._active = False
        self.frames = 0
        self.opens = 0

    @property
    def sample_rate(self) -> int:
        return 16_000

    @property
    def channels(self) -> int:
        return 1

    @property
    def is_active(self) -> bool:
        return self._active

    async def start(self) -> None:
        self.opens += 1
        self._active = True

    async def stop(self) -> None:
        self._active = False

    async def stream_chunks(self) -> AsyncIterator[bytes]:
        while self._active:
            self.frames += 1
            yield bytes(2_560)
            await asyncio.sleep(0)


class _WakeWords(WakeWordSource):
    def __init__(self, input_device: _Input, output: _Output) -> None:
        self._input = input_device
        self._output = output

    @property
    def phrase(self) -> str:
        return "hey mycroft"

    async def detections(self) -> AsyncIterator[WakeWordDetection]:
        while self._input.frames < 3:
            await asyncio.sleep(0)
        yield WakeWordDetection(self._input.frames - 1, 0.9, "hey_mycroft")
        await self._output.first_chunk.wait()
        yield WakeWordDetection(self._input.frames - 1, 0.9, "hey_mycroft")
        await self._output.finished.wait()
        await asyncio.sleep(0)


class _SpeechToText(SpeechToText):
    def __init__(self) -> None:
        self.calls = 0

    async def transcribe(
        self, audio: AsyncIterable[bytes]
    ) -> AsyncIterator[Transcription]:
        await anext(aiter(audio))
        self.calls += 1
        yield Transcription("draft", False, TranscriptionKind.EAGER_END)
        yield Transcription(
            f"Hey Mycroft command {self.calls}", True, TranscriptionKind.END
        )


class _LanguageModel:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def respond(self, text: str) -> AsyncIterator[str]:
        self.calls.append(text)
        value = "A" if len(self.calls) == 1 else "B"
        for _ in range(20):
            yield value
            await asyncio.sleep(0.001)


class _TextToSpeech(TextToSpeech):
    async def synthesize(self, text: AsyncIterable[str]) -> AsyncIterator[bytes]:
        async for chunk in text:
            yield chunk.encode()


class _Output(AudioOutput):
    def __init__(self) -> None:
        self.first_chunk = asyncio.Event()
        self.finished = asyncio.Event()
        self.timeline: list[bytes | str] = []
        self._finishes = 0

    @property
    def is_playing(self) -> bool:
        return bool(self.timeline)

    async def start(self, *, sample_rate: int, channels: int) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def play_chunk(self, chunk: bytes) -> None:
        self.timeline.append(chunk)
        self.first_chunk.set()

    async def finish_response(self) -> None:
        self._finishes += 1
        if self._finishes == 1:
            self.finished.set()

    async def clear_buffer(self) -> None:
        self.timeline.append("clear")


def test_barge_in_cancels_old_audio_and_reuses_the_capture_loop() -> None:
    async def run() -> tuple[_Input, _SpeechToText, _LanguageModel, _Output, TurnState]:
        input_device = _Input()
        output = _Output()
        stt = _SpeechToText()
        llm = _LanguageModel()
        controller = TurnController(
            audio_hub=AudioHub(input_device),
            wake_word=_WakeWords(input_device, output),
            speech_to_text=stt,
            llm=llm,
            text_to_speech=_TextToSpeech(),
            playback=PlaybackCoordinator(output),
            event_bus=EventBus(),
        )
        await controller.run()
        return input_device, stt, llm, output, controller.state

    input_device, stt, llm, output, state = asyncio.run(run())

    first_clear = output.timeline.index("clear")
    after_barge_in = output.timeline[first_clear + 1 :]
    assert input_device.opens == 1
    assert stt.calls == 2
    assert llm.calls == ["command 1", "command 2"]
    assert b"A" not in after_barge_in
    assert b"B" in after_barge_in
    assert state is TurnState.ARMED
