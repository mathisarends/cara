import asyncio

from voice.audio.ports import AudioController, AudioOutput, AudioPlayback, VolumeControl


class AudioPlayer(AudioPlayback, VolumeControl):
    """Delegates playback to an audio sink selected at runtime."""

    def __init__(
        self,
        *controllers: AudioController,
        active_output: AudioOutput | None = None,
    ) -> None:
        if not controllers:
            raise ValueError("At least one audio controller is required.")
        self._controllers: dict[AudioOutput, AudioController] = {}
        for controller in controllers:
            self.register_output(controller)
        self._active_output = active_output or next(iter(self._controllers))
        if self._active_output not in self._controllers:
            raise ValueError(self._unknown_output_message(self._active_output))

    @property
    def active_output(self) -> AudioOutput:
        return self._active_output

    @property
    def available_outputs(self) -> tuple[AudioOutput, ...]:
        return tuple(self._controllers)

    @property
    def has_multiple_outputs(self) -> bool:
        return len(self._controllers) > 1

    def describe_outputs(self) -> str:
        return ", ".join(output.value for output in self._controllers)

    def register_output(
        self,
        controller: AudioController,
        *,
        activate: bool = False,
    ) -> None:
        output = controller.output
        if output in self._controllers:
            raise ValueError(f"Audio output {output.value!r} is already registered.")
        self._controllers[output] = controller
        if activate:
            self._active_output = output

    def set_output(self, output: AudioOutput) -> None:
        if output not in self._controllers:
            raise ValueError(self._unknown_output_message(output))
        self._active_output = output

    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        controller = self._controllers[self._active_output]
        await controller.play(audio, cancel=cancel)

    async def get_volume(self) -> float:
        controller = self._controllers[self._active_output]
        return await controller.get_volume()

    async def set_volume(self, volume: float) -> None:
        controller = self._controllers[self._active_output]
        await controller.set_volume(volume)

    def _unknown_output_message(self, output: AudioOutput) -> str:
        available = ", ".join(item.value for item in self._controllers)
        return (
            f"Audio output {output.value!r} is not configured. "
            f"Available outputs: {available}."
        )
