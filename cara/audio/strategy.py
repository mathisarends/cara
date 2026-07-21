import asyncio
from collections.abc import Mapping

from cara.audio.ports import AudioOutputStrategy


class AudioPlayer(AudioOutputStrategy):
    """Delegates playback to an audio output strategy selected at runtime."""

    def __init__(
        self,
        strategies: Mapping[str, AudioOutputStrategy],
        *,
        active_output: str | None = None,
    ) -> None:
        if not strategies:
            raise ValueError("At least one audio output strategy is required.")
        if any(not name.strip() for name in strategies):
            raise ValueError("Audio output names must not be empty.")

        self._strategies = dict(strategies)
        self._active_output = active_output or next(iter(self._strategies))
        if self._active_output not in self._strategies:
            raise ValueError(self._unknown_output_message(self._active_output))

    @property
    def active_output(self) -> str:
        return self._active_output

    @property
    def available_outputs(self) -> tuple[str, ...]:
        return tuple(self._strategies)

    def register_output(
        self,
        name: str,
        strategy: AudioOutputStrategy,
        *,
        activate: bool = False,
    ) -> None:
        if not name.strip():
            raise ValueError("Audio output name must not be empty.")
        if name in self._strategies:
            raise ValueError(f"Audio output {name!r} is already registered.")
        self._strategies[name] = strategy
        if activate:
            self._active_output = name

    def set_output(self, name: str) -> None:
        if name not in self._strategies:
            raise ValueError(self._unknown_output_message(name))
        self._active_output = name

    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        strategy = self._strategies[self._active_output]
        await strategy.play(audio, cancel=cancel)

    def _unknown_output_message(self, name: str) -> str:
        available = ", ".join(self._strategies)
        return f"Unknown audio output {name!r}. Available outputs: {available}."
