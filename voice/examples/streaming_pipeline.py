"""Runnable tour of the voice pipeline without hardware or provider accounts.

Run from the repository root with:

    uv run python voice/examples/streaming_pipeline.py

The trace demonstrates that capture remains open, eager STT updates do not start
the model, and text and PCM stream incrementally.
"""

import asyncio
from collections.abc import AsyncIterable, AsyncIterator

from voice.audio import AudioBridge, AudioHub, AudioInput, AudioOutput
from voice.events import SessionEnded, SessionStarted
from voice.events.bus import EventBus
from voice.events.models import VoiceResourcesClosing
from voice.handler import WakeWordHandler
from voice.llm import EchoLanguageModel
from voice.pipeline import SpeechPipeline, TurnManager
from voice.stt import SpeechToText, Transcription, TranscriptionKind
from voice.tts import TextToSpeech
from voice.wakeword import WakeWordDetection


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
    def __init__(self, microphone: _ScriptedMicrophone) -> None:
        self._microphone = microphone

    @property
    def phrase(self) -> str:
        return "hey mycroft"

    async def detections(self) -> AsyncIterator[WakeWordDetection]:
        await _wait_for_frames(self._microphone, 4)
        print("wake: detected")
        yield WakeWordDetection(3, 0.91, "hey_mycroft")

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
        text = "Hey Mycroft erzähle eine lange Geschichte"
        print(f"stt[{self._turn}]: final transcript: {text!r}")
        yield Transcription(text, True, TranscriptionKind.END)


class _TraceTextToSpeech(TextToSpeech):
    async def synthesize(self, text: AsyncIterable[str]) -> AsyncIterator[bytes]:
        async for delta in text:
            print(f"tts: received model delta {delta!r}")
            yield delta.encode()
            await asyncio.sleep(0.01)


class _TraceOutput(AudioOutput):
    def __init__(self) -> None:
        self._active = False
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
    microphone = _ScriptedMicrophone()
    output = _TraceOutput()
    event_bus = EventBus()
    audio_hub = AudioHub(microphone)
    AudioBridge(
        event_bus=event_bus,
        audio_hub=audio_hub,
        output_device=output,
    )
    wake_words = _ScriptedWakeWords(microphone)
    pipeline = SpeechPipeline(
        wake_word_phrase=wake_words.phrase,
        speech_to_text=_ScriptedSpeechToText(),
        llm=EchoLanguageModel(),
        text_to_speech=_TraceTextToSpeech(),
        event_bus=event_bus,
    )
    TurnManager(
        audio_hub=audio_hub,
        pipeline=pipeline,
        event_bus=event_bus,
    )
    wake_word_handler = WakeWordHandler(
        event_bus=event_bus,
        source=wake_words,
    )
    await event_bus.dispatch(SessionStarted())
    task = asyncio.create_task(wake_word_handler.run())
    while output.completed < 1:
        await asyncio.sleep(0.01)
    await event_bus.dispatch(SessionEnded())
    wake_word_handler.close()
    await event_bus.dispatch(VoiceResourcesClosing())
    await task
    print(f"capture: total opens = {microphone.opens}")


if __name__ == "__main__":
    asyncio.run(_run())
