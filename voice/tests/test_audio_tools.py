import asyncio

from cara.tools import create_tool_context, create_tools
from voice.audio import AudioOutput, AudioPlayer
from voice.tools import build_audio_tools


class SilentOutput:
    def __init__(self, output: AudioOutput) -> None:
        self._output = output
        self.volume = 1.0

    @property
    def output(self) -> AudioOutput:
        return self._output

    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        pass

    async def get_volume(self) -> float:
        return self.volume

    async def set_volume(self, volume: float) -> None:
        self.volume = volume


def test_audio_tools_follow_injected_player_availability() -> None:
    context = create_tool_context(AudioPlayer(SilentOutput(AudioOutput.LOCAL)))
    tools = create_tools(context)
    tools.merge(build_audio_tools())

    available = {schema.name for schema in tools.get_schema()}
    assert "get_volume" in available
    assert "set_audio_output" not in available

    context.provide(
        AudioPlayer(SilentOutput(AudioOutput.LOCAL), SilentOutput(AudioOutput.SONOS))
    )

    assert "set_audio_output" in {schema.name for schema in tools.get_schema()}
