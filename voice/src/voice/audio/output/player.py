import asyncio
import io
import wave
from typing import cast

from voice.audio.output.playback import AudioPlayback, VolumeControl
from voice.audio.ports import AudioOutput

_PLAYBACK_CHUNK_SECONDS = 0.01
_PCM_SAMPLE_WIDTH = 2


class AudioPlayer(AudioPlayback, VolumeControl):
    """Decodes WAV responses and routes their PCM chunks to an audio output."""

    def __init__(self, output: AudioOutput) -> None:
        self._output = output

    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        output = self._output
        try:
            with wave.open(io.BytesIO(audio), "rb") as wav_file:
                if wav_file.getsampwidth() != _PCM_SAMPLE_WIDTH:
                    raise ValueError(
                        "Audio outputs require signed 16-bit PCM WAV audio."
                    )
                sample_rate = wav_file.getframerate()
                channels = wav_file.getnchannels()
                await output.start(sample_rate=sample_rate, channels=channels)
                frames_per_chunk = max(1, round(sample_rate * _PLAYBACK_CHUNK_SECONDS))
                while chunk := wav_file.readframes(frames_per_chunk):
                    if cancel is not None and cancel.is_set():
                        await output.clear_buffer()
                        return
                    await output.play_chunk(chunk)
            await _finish(output, cancel)
        except asyncio.CancelledError:
            await asyncio.shield(output.clear_buffer())
            raise

    async def stop(self) -> None:
        await self._output.stop()

    async def get_volume(self) -> float:
        output = cast(VolumeControl, self._output)
        return await output.get_volume()

    async def set_volume(self, volume: float) -> None:
        output = cast(VolumeControl, self._output)
        await output.set_volume(volume)


async def _finish(output: AudioOutput, cancel: asyncio.Event | None) -> None:
    if cancel is None:
        await output.finish_response()
        return

    finished = asyncio.create_task(output.finish_response())
    interrupted = asyncio.create_task(cancel.wait())
    try:
        done, _ = await asyncio.wait(
            (finished, interrupted), return_when=asyncio.FIRST_COMPLETED
        )
        if finished in done:
            await finished
        else:
            await output.clear_buffer()
    finally:
        for task in (finished, interrupted):
            if not task.done():
                task.cancel()
        await asyncio.gather(finished, interrupted, return_exceptions=True)
