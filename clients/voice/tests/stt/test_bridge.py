import asyncio
from collections.abc import AsyncIterable, AsyncIterator
from typing import cast

from voice.audio import AudioOverrunError, AudioReader, BufferedAudioInput
from voice.events import UserTranscriptionRequested, VoiceTurnTimedOut
from voice.events.bus import EventBus
from voice.stt import SpeechToText, SpeechToTextBridge, Transcription


class _Reader:
    def __aiter__(self) -> AsyncIterator:
        return self

    async def __anext__(self):
        await asyncio.Event().wait()

    async def aclose(self) -> None:
        pass


class _BufferedInput:
    async def open_reader(self, **_: object) -> AudioReader:
        return cast(AudioReader, _Reader())


class _OverrunningSpeechToText(SpeechToText):
    async def transcribe(
        self, audio: AsyncIterable[bytes]
    ) -> AsyncIterator[Transcription]:
        del audio
        raise AudioOverrunError("reader fell behind")
        yield


def test_audio_overrun_ends_transcription_without_failing_the_request() -> None:
    async def run() -> list[VoiceTurnTimedOut]:
        event_bus = EventBus()
        SpeechToTextBridge(
            event_bus=event_bus,
            buffered_audio_input=cast(BufferedAudioInput, _BufferedInput()),
            speech_to_text=_OverrunningSpeechToText(),
        )
        timed_out: list[VoiceTurnTimedOut] = []

        async def capture(event: VoiceTurnTimedOut) -> None:
            timed_out.append(event)

        event_bus.on(VoiceTurnTimedOut, capture)
        await event_bus.request(
            UserTranscriptionRequested(
                turn_id=4,
                sequence=892,
                pre_roll_seconds=0.16,
                speech_start_timeout=8.0,
            )
        )
        return timed_out

    assert asyncio.run(run()) == [VoiceTurnTimedOut(turn_id=4)]
