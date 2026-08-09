import agenttoolkit
from agenttoolkit import Inject, description_from_context, provided, requires
from pydantic import Field

from cara.tools import ToolParams
from voice.audio import AudioOutput, AudioPlayer


class SetAudioOutputParams(ToolParams):
    output: AudioOutput = Field(
        description="Configured audio sink to activate.",
    )


class SetVolumeParams(ToolParams):
    level: float = Field(
        ge=0.0,
        le=1.0,
        description="Target playback volume, from 0.0 (silent) to 1.0 (full).",
    )


def build_audio_tools() -> agenttoolkit.Tools:
    """Build audio-control actions for merging into an agent's tool catalog."""
    tools = agenttoolkit.Tools()
    _register_audio_tools(tools)
    return tools


def _register_audio_tools(tools: agenttoolkit.Tools) -> None:
    @tools.action(
        description=description_from_context(
            AudioPlayer,
            render=lambda player: (
                "Switch audio playback to another configured audio sink. "
                f"Available output names: {player.describe_outputs()}."
            ),
            fallback="Switch audio playback to another configured audio sink.",
        ),
        params=SetAudioOutputParams,
        available_when=requires(
            AudioPlayer, predicate=lambda player: player.has_multiple_outputs
        ),
    )
    async def set_audio_output(
        params: SetAudioOutputParams, player: Inject[AudioPlayer]
    ) -> str:
        player.set_output(params.output)
        return f"Audio output switched to {params.output.value!r}."

    @tools.action(
        description=(
            "Frage die aktuelle Wiedergabelautstärke des aktiven "
            "Audio-Ausgangs ab, als Wert von 0.0 bis 1.0."
        ),
        available_when=provided(AudioPlayer),
    )
    async def get_volume(player: Inject[AudioPlayer]) -> str:
        level = await player.get_volume()
        return f"{level:.2f}"

    @tools.action(
        description=(
            "Stelle die Wiedergabelautstärke des aktiven Audio-Ausgangs auf "
            "einen Zielwert. "
            "Frage vorher get_volume ab, um den aktuellen Wert zu kennen."
        ),
        params=SetVolumeParams,
        available_when=provided(AudioPlayer),
    )
    async def set_volume(params: SetVolumeParams, player: Inject[AudioPlayer]) -> str:
        await player.set_volume(params.level)
        return f"Lautstärke ist jetzt {round(params.level * 100)}%."
