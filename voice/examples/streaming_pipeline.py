"""Runnable tour of the voice pipeline without hardware or provider accounts.

Run from the repository root with:

    uv run python voice/examples/streaming_pipeline.py

The trace demonstrates that capture remains open, eager STT updates do not start
the model, text and PCM stream incrementally, and a second wake word interrupts
the first response before starting another STT turn.
"""

import asyncio
from collections.abc import AsyncIterable, AsyncIterator

from transitbus import EventBus

from voice.audio import AudioHub, AudioInput, AudioOutput, PlaybackCoordinator
from voice.llm import EchoLanguageModel
from voice.pipeline import TurnController, WakeWordDetection
from voice.stt import SpeechToText, Transcription, TranscriptionKind
from voice.tts import TextToSpeech


class _ScriptedMicrophone(AudioInput):
    def __init__(self) -> None:
        self._active = False
        self._frames_sent = 0
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

    @property
    def frames_sent(self) -> int:
        return self._frames_sent

    async def start(self) -> None:
        self.opens += 1
        self._active = True
        print("capture: opened once")

    async def stop(self) -> None:
        self._active = False

    async def stream_chunks(self) -> AsyncIterator[bytes]:
        while self._active:
            sequence = self._frames_sent
            self._frames_sent += 1
            yield sequence.to_bytes(2, "little") * 1_280
            await asyncio.sleep(0.005)


class _ScriptedWakeWords:
    def __init__(
        self, microphone: _ScriptedMicrophone, first_audio: asyncio.Event
    ) -> None:
        self._microphone = microphone
        self._first_audio = first_audio

    @property
    def phrase(self) -> str:
        return "hey mycroft"

    async def detections(self) -> AsyncIterator[WakeWordDetection]:
        await _wait_for_frames(self._microphone, 4)
        print("wake: first detection")
        yield WakeWordDetection(3, 0.91, "hey_mycroft")

        await self._first_audio.wait()
        sequence = self._microphone.frames_sent - 1
        print("wake: barge-in while the first response is speaking")
        yield WakeWordDetection(sequence, 0.94, "hey_mycroft")

        while self._microphone.is_active:
            await asyncio.sleep(0.01)


class _ScriptedSpeechToText(SpeechToText):
    def __init__(self) -> None:
        self._turn = 0

    async def transcribe(
        self, audio: AsyncIterable[bytes]
    ) -> AsyncIterator[Transcription]:
        self._turn += 1
        first_frame = await anext(aiter(audio))
        sequence = int.from_bytes(first_frame[:2], "little")
        print(f"stt[{self._turn}]: starts with pre-roll frame {sequence}")
        yield Transcription("", False, TranscriptionKind.START)
        yield Transcription("vorläufig", False, TranscriptionKind.EAGER_END)
        print(f"stt[{self._turn}]: eager end (the model is still idle)")
        await asyncio.sleep(0.02)
        text = (
            "Hey Mycroft erzähle eine lange Geschichte"
            if self._turn == 1
            else "Hey Mycroft sage kurz tschüss"
        )
        print(f"stt[{self._turn}]: final transcript: {text!r}")
        yield Transcription(text, True, TranscriptionKind.END)


class _TraceTextToSpeech(TextToSpeech):
    async def synthesize(self, text: AsyncIterable[str]) -> AsyncIterator[bytes]:
        async for delta in text:
            print(f"tts: received model delta {delta!r}")
            yield delta.encode()
            await asyncio.sleep(0.01)


class _TraceOutput(AudioOutput):
    def __init__(self, first_audio: asyncio.Event) -> None:
        self._active = False
        self._first_audio = first_audio
        self.completed = 0

    @property
    def is_playing(self) -> bool:
        return self._active

    async def start(self, *, sample_rate: int, channels: int) -> None:
        self._active = True
        print(f"output: started raw PCM at {sample_rate} Hz/{channels} channel")

    async def stop(self) -> None:
        self._active = False

    async def play_chunk(self, chunk: bytes) -> None:
        self._first_audio.set()
        print(f"output: PCM {chunk!r}")

    async def finish_response(self) -> None:
        self.completed += 1
        print("output: response finished")

    async def clear_buffer(self) -> None:
        print("output: pending PCM cleared")


async def _wait_for_frames(microphone: _ScriptedMicrophone, minimum: int) -> None:
    while microphone.frames_sent < minimum:
        await asyncio.sleep(0)


async def _run() -> None:
    first_audio = asyncio.Event()
    microphone = _ScriptedMicrophone()
    output = _TraceOutput(first_audio)
    controller = TurnController(
        hub=AudioHub(microphone),
        wake_words=_ScriptedWakeWords(microphone, first_audio),
        speech_to_text=_ScriptedSpeechToText(),
        llm=EchoLanguageModel(),
        text_to_speech=_TraceTextToSpeech(),
        playback=PlaybackCoordinator(output),
        event_bus=EventBus(),
    )
    task = asyncio.create_task(controller.run())
    while output.completed < 1:
        await asyncio.sleep(0.01)
    await controller.close()
    await task
    print(f"capture: total opens = {microphone.opens}")


if __name__ == "__main__":
    asyncio.run(_run())
