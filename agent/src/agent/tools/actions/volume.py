from agenttoolkit import Inject, Tools, provided
from pydantic import Field

from agent.tools.params import ToolParams
from voice.audio import VolumeControl


class VolumeParams(ToolParams):
    volume: int = Field(
        ge=0, le=100, description="Playback volume in percent, from 0 to 100."
    )


def register_volume_tools(tools: Tools) -> None:
    @tools.action(
        description=(
            "Read the current playback volume in percent. Call this before a "
            "relative change such as 'a bit quieter'."
        ),
        available_when=provided(VolumeControl),
    )
    async def get_volume(control: Inject[VolumeControl]) -> str:
        return _render_volume(await control.get_volume())

    @tools.action(
        description="Set the playback volume to a percentage.",
        params=VolumeParams,
        available_when=provided(VolumeControl),
    )
    async def set_volume(params: VolumeParams, control: Inject[VolumeControl]) -> str:
        await control.set_volume(params.volume)
        return _render_volume(params.volume)


def _render_volume(volume: int) -> str:
    return f"Lautstärke: {volume} %."
