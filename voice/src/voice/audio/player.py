import asyncio

from voice.audio.ports import AudioOutput, AudioPlayback, AudioSink


class AudioPlayer(AudioPlayback):
    """Delegates playback to an audio sink selected at runtime."""

    def __init__(
        self,
        *sinks: AudioSink,
        active_output: AudioOutput | None = None,
    ) -> None:
        if not sinks:
            raise ValueError("At least one audio sink is required.")
        self._sinks: dict[AudioOutput, AudioSink] = {}
        for sink in sinks:
            self.register_output(sink)
        self._active_output = active_output or next(iter(self._sinks))
        if self._active_output not in self._sinks:
            raise ValueError(self._unknown_output_message(self._active_output))

    @property
    def active_output(self) -> AudioOutput:
        return self._active_output

    @property
    def available_outputs(self) -> tuple[AudioOutput, ...]:
        return tuple(self._sinks)

    @property
    def has_multiple_outputs(self) -> bool:
        return len(self._sinks) > 1

    def describe_outputs(self) -> str:
        return ", ".join(output.value for output in self._sinks)

    def register_output(
        self,
        sink: AudioSink,
        *,
        activate: bool = False,
    ) -> None:
        output = sink.output
        if output in self._sinks:
            raise ValueError(f"Audio output {output.value!r} is already registered.")
        self._sinks[output] = sink
        if activate:
            self._active_output = output

    def set_output(self, output: AudioOutput) -> None:
        if output not in self._sinks:
            raise ValueError(self._unknown_output_message(output))
        self._active_output = output

    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        sink = self._sinks[self._active_output]
        await sink.play(audio, cancel=cancel)

    async def get_volume(self) -> float:
        sink = self._sinks[self._active_output]
        return await sink.get_volume()

    async def set_volume(self, volume: float) -> None:
        sink = self._sinks[self._active_output]
        await sink.set_volume(volume)

    def _unknown_output_message(self, output: AudioOutput) -> str:
        available = ", ".join(item.value for item in self._sinks)
        return (
            f"Audio output {output.value!r} is not configured. "
            f"Available outputs: {available}."
        )
