# Cara Agent Plugin API

`agent-plugin-api` is the dependency boundary between the Cara Gateway and an
installed agent plugin. It contains only immutable request/context models,
streamed agent events, and structural protocols — no FastAPI, Dishka,
SQLModel, or Gateway implementation code.

The Gateway owns sessions and transcripts. A plugin's `AgentRunner` receives
only the current turn as an `AgentRunRequest`; when it needs earlier
conversation history, it reads it through the read-only `AgentSessionReader`
supplied in `AgentPluginContext`. A plugin never gets write access to session
state — it streams `AgentEvent`s back and the Gateway persists them.

## Table of contents

- [Installation](#installation)
- [Concepts](#concepts)
- [Request and context models](#request-and-context-models)
- [Streamed events](#streamed-events)
- [The plugin contract](#the-plugin-contract)
- [Writing a plugin](#writing-a-plugin)
- [Versioning](#versioning)

## Installation

```bash
pip install agent-plugin-api
```

Requires Python 3.13. The package has no runtime dependencies of its own.

## Concepts

```text
Gateway
  │  AgentRunRequest(session, turn_id, input_id, input)
  ▼
AgentRunner.run(request) -> AsyncIterator[AgentEvent]
  │
  │  context_for_turn(session_id, input_id) via AgentSessionReader
  ▼
AgentContext  (read-only, entries strictly before input_id)
```

A plugin package should import its complete Gateway-facing API from
`agent_plugin_api`, never from modules below `gateway`. This keeps a plugin
installable and testable as its own wheel, independent of the Gateway's own
dependency tree.

## Request and context models

```python
from agent_plugin_api import (
    AgentChannelRef,
    AgentContext,
    AgentContextEntry,
    AgentRunRequest,
    AgentSessionRef,
)
```

| Type | Purpose |
| --- | --- |
| `AgentChannelRef` | Identifies the client surface a turn came from — `name` (`"voice"`, `"cli"`, ...) plus an optional `account_id`. |
| `AgentSessionRef` | A Gateway-issued session `id` paired with its `AgentChannelRef`. |
| `AgentRunRequest` | One turn to execute: `session`, `turn_id`, `input_id`, the new `input` text, and free-form `turn_metadata`. |
| `AgentContext` | A read-only view of everything before the current turn: an ordered tuple of `AgentContextEntry` plus `session_metadata`. |
| `AgentContextEntry` | `AgentUserMessage \| AgentAssistantMessage \| AgentToolCallSequence` — the three shapes conversation history can take. |
| `AgentToolCall` / `AgentToolCallSequence` | A completed or failed tool invocation (`call_id`, `name`, `arguments`, `state`, `result`, `error`), grouped into the sequence the assistant issued them in. |

`AgentSessionReader.context_for_turn(session_id, input_id)` returns entries
**strictly before** `input_id`, so the input the plugin is currently handling
never appears twice.

## Streamed events

```python
from agent_plugin_api import AgentEvent, ChatDelta, ChatCompleted, ToolCallStarted, ToolCallCompleted
```

`AgentRunner.run()` yields a stream of `AgentEvent`, the union of:

| Event | Carries |
| --- | --- |
| `ChatDelta` | One streamed text chunk. |
| `ChatCompleted` | The full assistant text (the concatenation of prior deltas) and a `finish_reason`. |
| `ToolCallStarted` | `call_id`, tool `name`, and `arguments` for a tool invocation the agent started. |
| `ToolCallCompleted` | The same `call_id`/`name`, plus `result` and `is_error`. |

The Gateway persists these events and forwards them to subscribed clients —
it is the single translation point between a plugin's internal event model
and the wire protocol; a plugin never talks WebSocket or JSON-RPC directly.

## The plugin contract

```python
from agent_plugin_api import AgentPlugin, AgentPluginContext, AgentRunner
```

```python
class AgentRunner(Protocol):
    def run(self, request: AgentRunRequest) -> AsyncIterator[AgentEvent]: ...
    async def close(self) -> None: ...


class AgentPlugin(Protocol):
    api_version: int

    def create(
        self,
        config: Mapping[str, Any],
        context: AgentPluginContext,
    ) -> AgentRunner: ...
```

- `AgentPlugin.create()` builds one `AgentRunner` per Gateway process from the
  plugin's configuration section and the `AgentPluginContext` (currently just
  the `sessions: AgentSessionReader` capability).
- `AgentRunner.run()` executes one turn and streams its events; cancelling the
  async iterator is how the Gateway cancels an in-flight turn.
- `AgentRunner.close()` is called once on Gateway shutdown so the plugin can
  release HTTP clients, sandbox processes, or model resources.

Both protocols are `@runtime_checkable`, so the Gateway's loader can validate
a loaded object with `isinstance()` before trusting it.

## Writing a plugin

An installed plugin registers a parameterless `create_plugin()` factory in the
`cara.agent_plugins` entry-point group:

```toml
[project]
name = "cara-agent-plugin"
dependencies = ["agent-plugin-api"]

[project.entry-points."cara.agent_plugins"]
cara = "cara_agent_plugin:create_plugin"
```

```python
from collections.abc import Mapping
from typing import Any

from agent_plugin_api import AgentPlugin, AgentPluginContext, AgentRunner


class CaraAgentPlugin:
    api_version = 1

    def create(
        self,
        config: Mapping[str, Any],
        context: AgentPluginContext,
    ) -> AgentRunner:
        return CaraAgentRunner(config, sessions=context.sessions)


def create_plugin() -> AgentPlugin:
    return CaraAgentPlugin()
```

The factory is called exactly once per Gateway start; the loader validates it
before invoking it, then validates the `AgentPlugin` it returns.

## Versioning

`AGENT_PLUGIN_API_VERSION` is the current contract version. A plugin declares
the version it was built against via `AgentPlugin.api_version`; the Gateway
rejects a mismatched plugin at startup, before it can fail mid-turn.
