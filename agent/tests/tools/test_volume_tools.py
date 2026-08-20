import asyncio
from pathlib import Path

from agenttoolkit.builtins import LocalWorkspace

from agent.tools import build_tools, create_tool_context, create_tools
from voice.audio import VolumeControl


class _FakeVolumeControl(VolumeControl):
    def __init__(self, volume: int) -> None:
        self.volume = volume

    async def get_volume(self) -> int:
        return self.volume

    async def set_volume(self, volume: int) -> None:
        self.volume = volume


def test_volume_tools_are_unavailable_without_volume_control() -> None:
    tools = create_tools()

    assert {schema.name for schema in tools.get_schema()}.isdisjoint(
        {"get_volume", "set_volume"}
    )


def test_volume_tools_are_available_with_volume_control() -> None:
    tools = create_tools(create_tool_context(_FakeVolumeControl(50)))

    assert {"get_volume", "set_volume"} <= {
        schema.name for schema in tools.get_schema()
    }


def test_get_volume_reports_the_current_level() -> None:
    tools = create_tools(create_tool_context(_FakeVolumeControl(35)))

    result = asyncio.run(tools.execute("get_volume", {}))

    assert result == "Lautstärke: 35 %."


def test_set_volume_changes_the_output_level() -> None:
    control = _FakeVolumeControl(50)
    tools = create_tools(create_tool_context(control))

    result = asyncio.run(tools.execute("set_volume", {"volume": 60}))

    assert result == "Lautstärke: 60 %."
    assert control.volume == 60


def test_setting_a_volume_beyond_the_range_fails() -> None:
    control = _FakeVolumeControl(50)
    tools = create_tools(create_tool_context(control))

    result = asyncio.run(tools.execute("set_volume", {"volume": 120}))

    assert result.startswith("Tool failed:")
    assert control.volume == 50


def test_build_tools_wires_the_volume_control_into_the_context(tmp_path: Path) -> None:
    tools = build_tools(
        injected_dependencies=(_FakeVolumeControl(50),),
        workspace=LocalWorkspace(tmp_path),
    )

    assert {"get_volume", "set_volume"} <= {
        schema.name for schema in tools.get_schema()
    }
