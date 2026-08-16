import agenttoolkit

from voice.tools.audio import register_output_tools, register_volume_tools


def create_tools() -> agenttoolkit.Tools:
    """Build the voice tool catalog for merging into an agent's tools."""
    tools = agenttoolkit.Tools()
    register_output_tools(tools)
    register_volume_tools(tools)
    return tools
