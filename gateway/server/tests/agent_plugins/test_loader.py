import importlib.metadata
from collections.abc import Mapping
from typing import Any

import pytest

from agent_plugin_api import (
    AGENT_PLUGIN_API_VERSION,
    AgentPluginContext,
    AgentRunner,
    AgentRunRequest,
)
from gateway.agent_plugins import AgentPluginLoadError, load_agent_plugin


class _Runner:
    def run(self, request: AgentRunRequest):
        del request
        raise NotImplementedError

    async def close(self) -> None:
        pass


class _Plugin:
    api_version = AGENT_PLUGIN_API_VERSION

    def create(
        self,
        config: Mapping[str, Any],
        context: AgentPluginContext,
    ) -> AgentRunner:
        del config, context
        return _Runner()


class _EntryPoint:
    def __init__(self, name: str, value: object) -> None:
        self.name = name
        self._value = value

    def load(self) -> object:
        return self._value


def _entry_points(monkeypatch: pytest.MonkeyPatch, *values: _EntryPoint) -> None:
    monkeypatch.setattr(
        importlib.metadata,
        "entry_points",
        lambda **_: values,
    )


def test_loader_returns_the_single_compatible_plugin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin = _Plugin()
    _entry_points(monkeypatch, _EntryPoint("custom", lambda: plugin))

    assert load_agent_plugin("custom") is plugin


def test_loader_rejects_an_unknown_plugin(monkeypatch: pytest.MonkeyPatch) -> None:
    _entry_points(monkeypatch)

    with pytest.raises(AgentPluginLoadError, match="not installed"):
        load_agent_plugin("missing")


def test_loader_rejects_duplicate_plugin_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _entry_points(
        monkeypatch,
        _EntryPoint("custom", lambda: _Plugin()),
        _EntryPoint("custom", lambda: _Plugin()),
    )

    with pytest.raises(AgentPluginLoadError, match="registered 2 times"):
        load_agent_plugin("custom")


def test_loader_rejects_an_incompatible_api_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin = _Plugin()
    plugin.api_version = AGENT_PLUGIN_API_VERSION + 1
    _entry_points(monkeypatch, _EntryPoint("custom", lambda: plugin))

    with pytest.raises(AgentPluginLoadError, match="uses API version"):
        load_agent_plugin("custom")


def test_loader_rejects_an_entry_point_without_a_plugin_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _entry_points(monkeypatch, _EntryPoint("custom", object()))

    with pytest.raises(AgentPluginLoadError, match="plugin factory"):
        load_agent_plugin("custom")


def test_loader_rejects_an_object_without_the_plugin_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _entry_points(monkeypatch, _EntryPoint("custom", lambda: object()))

    with pytest.raises(AgentPluginLoadError, match="plugin contract"):
        load_agent_plugin("custom")


def test_loader_reports_plugin_factory_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail() -> _Plugin:
        raise RuntimeError("broken factory")

    _entry_points(monkeypatch, _EntryPoint("custom", fail))

    with pytest.raises(AgentPluginLoadError, match="could not be created"):
        load_agent_plugin("custom")
