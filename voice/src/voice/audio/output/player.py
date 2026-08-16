import asyncio
import io
import wave
from typing import cast

from voice.audio.output.destination import AudioDestination, RoutedAudioOutput
from voice.audio.output.playback import AudioPlayback, VolumeControl

_PLAYBACK_CHUNK_SECONDS = 0.01
_PCM_SAMPLE_WIDTH = 2


class AudioPlayer(AudioPlayback, VolumeControl):
    """Decodes WAV responses and routes their PCM chunks to an audio output."""

    def __init__(
        self,
        *outputs: RoutedAudioOutput,
        active_output: AudioDestination | None = None,
    ) -> None:
        if not outputs:
            raise ValueError("At least one audio output is required.")
        self._outputs: dict[AudioDestination, RoutedAudioOutput] = {}
        for output in outputs:
            self.register_output(output)
        self._active_output = active_output or next(iter(self._outputs))
        if self._active_output not in self._outputs:
            raise ValueError(self._unknown_output_message(self._active_output))

    @property
    def active_output(self) -> AudioDestination:
        return self._active_output

    @property
    def available_outputs(self) -> tuple[AudioDestination, ...]:
        return tuple(self._outputs)

    @property
    def has_multiple_outputs(self) -> bool:
        return len(self._outputs) > 1

    def describe_outputs(self) -> str:
        return ", ".join(output.value for output in self._outputs)

    def register_output(
        self,
        output: RoutedAudioOutput,
        *,
        activate: bool = False,
    ) -> None:
        destination = output.destination
        if destination in self._outputs:
            raise ValueError(
                f"Audio output {destination.value!r} is already registered."
            )
        self._outputs[destination] = output
        if activate:
            self._active_output = destination

    def set_output(self, output: AudioDestination) -> None:
        if output not in self._outputs:
            raise ValueError(self._unknown_output_message(output))
        self._active_output = output

    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        output = self._outputs[self._active_output]
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
        await asyncio.gather(*(output.stop() for output in self._outputs.values()))

    async def get_volume(self) -> float:
        output = cast(VolumeControl, self._outputs[self._active_output])
        return await output.get_volume()

    async def set_volume(self, volume: float) -> None:
        output = cast(VolumeControl, self._outputs[self._active_output])
        await output.set_volume(volume)

    def _unknown_output_message(self, output: AudioDestination) -> str:
        available = ", ".join(item.value for item in self._outputs)
        return (
            f"Audio output {output.value!r} is not configured. "
            f"Available outputs: {available}."
        )


async def _finish(output: RoutedAudioOutput, cancel: asyncio.Event | None) -> None:
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
