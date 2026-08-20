import importlib.metadata

from agent_plugin_api import (
    AGENT_PLUGIN_API_VERSION,
    AgentPlugin,
)

_ENTRY_POINT_GROUP = "cara.agent_plugins"


class AgentPluginLoadError(RuntimeError):
    pass


def load_agent_plugin(name: str) -> AgentPlugin:
    matches = tuple(
        entry_point
        for entry_point in importlib.metadata.entry_points(group=_ENTRY_POINT_GROUP)
        if entry_point.name == name
    )
    if not matches:
        raise AgentPluginLoadError(f"Agent plugin '{name}' is not installed")
    if len(matches) > 1:
        raise AgentPluginLoadError(
            f"Agent plugin '{name}' is registered {len(matches)} times"
        )

    try:
        plugin = matches[0].load()
    except Exception as error:
        raise AgentPluginLoadError(
            f"Agent plugin '{name}' could not be loaded"
        ) from error

    if not isinstance(plugin, AgentPlugin):
        raise AgentPluginLoadError(
            f"Agent plugin '{name}' does not implement the plugin contract"
        )
    if plugin.api_version != AGENT_PLUGIN_API_VERSION:
        raise AgentPluginLoadError(
            f"Agent plugin '{name}' uses API version {plugin.api_version}; "
            f"expected {AGENT_PLUGIN_API_VERSION}"
        )
    return plugin
