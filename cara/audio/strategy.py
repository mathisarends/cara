import asyncio

from cara.audio.ports import AudioOutput, AudioOutputStrategy, AudioPlayback


class AudioPlayer(AudioPlayback):
    """Delegates playback to an audio output strategy selected at runtime."""

    def __init__(
        self,
        *strategies: AudioOutputStrategy,
        active_output: AudioOutput | None = None,
    ) -> None:
        if not strategies:
            raise ValueError("At least one audio output strategy is required.")
        self._strategies: dict[AudioOutput, AudioOutputStrategy] = {}
        for strategy in strategies:
            self.register_output(strategy)
        self._active_output = active_output or next(iter(self._strategies))
        if self._active_output not in self._strategies:
            raise ValueError(self._unknown_output_message(self._active_output))

    @property
    def active_output(self) -> AudioOutput:
        return self._active_output

    @property
    def available_outputs(self) -> tuple[AudioOutput, ...]:
        return tuple(self._strategies)

    @property
    def has_multiple_outputs(self) -> bool:
        return len(self._strategies) > 1

    def describe_outputs(self) -> str:
        return ", ".join(output.value for output in self._strategies)

    def register_output(
        self,
        strategy: AudioOutputStrategy,
        *,
        activate: bool = False,
    ) -> None:
        output = strategy.output
        if output in self._strategies:
            raise ValueError(f"Audio output {output.value!r} is already registered.")
        self._strategies[output] = strategy
        if activate:
            self._active_output = output

    def set_output(self, output: AudioOutput) -> None:
        if output not in self._strategies:
            raise ValueError(self._unknown_output_message(output))
        self._active_output = output

    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        strategy = self._strategies[self._active_output]
        await strategy.play(audio, cancel=cancel)

    async def get_volume(self) -> float:
        strategy = self._strategies[self._active_output]
        return await strategy.get_volume()

    async def set_volume(self, volume: float) -> None:
        strategy = self._strategies[self._active_output]
        await strategy.set_volume(volume)

    def _unknown_output_message(self, output: AudioOutput) -> str:
        available = ", ".join(item.value for item in self._strategies)
        return f"Audio output {output.value!r} is not configured. Available outputs: {available}."
