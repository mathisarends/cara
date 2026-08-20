# agent

`agent` is Cara's model-agnostic conversational agent core: the stateful
tool-calling loop, system-prompt assembly from workspace markdown and skills,
and the application-specific tool catalog (filesystem, shell/sandbox,
weather, web search, volume, skills, model switching). It is registered as a
`cara.agent_plugins` entry point, so [`gateway`](../gateway) can discover and
drive it as a plugin without knowing anything about its internals — see
[Gateway plugin adapter](#gateway-plugin-adapter).

Tool infrastructure — registration, dependency injection, schema generation,
validation, middleware, skills, workspace access, and sandboxing — comes from
`mm-agenttoolkit`. This package only defines *what* tools Cara has and *how*
its turn loop and prompt are built.

## Table of contents

- [Public API](#public-api)
- [Module layout](#module-layout)
- [Running a turn](#running-a-turn)
- [Events](#events)
- [System prompt](#system-prompt)
- [Tools](#tools)
- [Sandbox](#sandbox)
- [Gateway plugin adapter](#gateway-plugin-adapter)

## Public API

```python
from agent import Agent, ModelSwitch, SystemPrompt
```

| Name | Purpose |
| --- | --- |
| `Agent` | Runs one stateful tool-calling agent loop and streams `AgentEvent`s. |
| `ModelSwitch` | The swappable `ChatModel` driving the agent, addressable by name. |
| `SystemPrompt` | Composes the system prompt from workspace markdown files, local time, memory, and skills. |

Subpackages are imported directly where needed rather than re-exported at the
top level: `agent.tools`, `agent.sandbox`, `agent.events`, `agent.messages`,
`agent.workspace`, `agent.plugin`.

## Module layout

```text
agent/src/agent/
├── __init__.py          Agent, ModelSwitch, SystemPrompt
├── agent.py               Agent: the stateful async tool-calling loop
├── events.py                AgentEvent union: TextDelta, ToolStarted, ToolCompleted, TurnCompleted
├── messages.py               MessageManager: append-only history + system prompt injection
├── models.py                  ModelSwitch: named ChatModel registry, swap-by-name
├── plugin.py                   cara.agent_plugins entry point: adapts Agent to agent_plugin_api
├── workspace.py                  resolve_workspace_root(): CARA_WORKSPACE_ROOT / ~/.cara/workspace
├── prompt/
│   ├── system_prompt.py           renders AGENTS/IDENTITY/SOUL/USER/TOOLS/MEMORY.md, daily memory, skills
│   └── local_time.py                renders the current date/time section
├── sandbox/
│   ├── config.py                    SandboxDefinition: pydantic model for the sandbox config section
│   └── factory.py                     builds an agenttoolkit DockerSandbox from a SandboxDefinition
└── tools/
    ├── factory.py                     AgentTools (owns the DockerSandbox lifecycle) + build_tools()
    ├── middleware.py                    ToolError, ToolFailure, ToolResultMiddleware
    ├── params.py                         ToolParams: shared pydantic base for tool arguments
    ├── actions/                          Cara's concrete tool definitions (see Tools)
    └── handler/                          ports + adapters injected into actions (Weather, WebSearch, ...)
```

## Running a turn

```python
from agent import Agent, ModelSwitch
from agent.tools import build_tools

models = ModelSwitch.single(my_chat_model, name="default")
tools = build_tools(injected_dependencies=(models,))

agent = Agent(models=models, tools=tools, workspace_root=workspace_root)

async for event in await agent.start_turn("What's the weather in Berlin?"):
    match event:
        case TextDelta(text=text):
            print(text, end="")
        case ToolStarted(name=name, arguments=args):
            print(f"\n[calling {name}({args})]")
        case ToolCompleted(name=name, result=result, is_error=is_error):
            print(f"[{name} -> {result!r}{' (error)' if is_error else ''}]")
        case TurnCompleted(text=text, finish_reason=reason):
            print(f"\n(done: {reason})")
```

`start_turn(text)` first calls `prepare_turn()`, which lazily opens the
Docker sandbox — guarded by a lock plus a shielded task so concurrent calls
share one preparation — appends the user message to history, and returns an
async generator backed by an internal queue. The actual loop
(`_run_loop`/`_run_turn`) runs as a background task:

1. Stream a completion from `self._models.current`, turning each text delta
   into a `TextDelta` event.
2. If the completion has no tool calls, append the assistant text to history
   and emit `TurnCompleted` — the turn is done.
3. Otherwise execute each tool call in sequence, emitting `ToolStarted` /
   `ToolCompleted` around every call, fold the results back into the message
   history as a tool round, and go back to step 1 for another completion.

Consuming the generator to a terminal event (or exhausting it) always tears
down the sandbox in a `finally`, so callers get automatic cleanup even on an
early `break` or exception. `agent.steer(text)` injects an additional user
message mid-turn (used for voice barge-in-style interaction); `agent.interrupt()`
cancels the running turn and forces teardown immediately.

## Events

```python
from agent.events import AgentEvent, TextDelta, ToolStarted, ToolCompleted, TurnCompleted
```

All frozen dataclasses:

| Event | Fields |
| --- | --- |
| `TextDelta` | `text` |
| `ToolStarted` | `name`, `call_id`, `arguments` |
| `ToolCompleted` | `name`, `call_id`, `result`, `is_error` |
| `TurnCompleted` | `text`, `finish_reason` |

`type AgentEvent = TextDelta \| TurnCompleted \| ToolStarted \| ToolCompleted`.
These are the agent's *internal* event model — `agent.plugin` translates them
1:1 into the [`agent_plugin_api`](../agent_plugin_api) event model the Gateway
persists and forwards to clients.

## System prompt

`SystemPrompt` composes, in order:

1. The base prompt — either an explicit override string, or the concatenation
   of `AGENTS.md`, `IDENTITY.md`, `SOUL.md`, `USER.md` from the workspace root.
2. A local-time section (current weekday/date/time).
3. Memory — `MEMORY.md` plus today's `memory/YYYY-MM-DD.md`, if present.
4. `TOOLS.md`.
5. The skills catalog, rendered from an injected `agenttoolkit.Skills`.

Missing or blank files are silently skipped. `MessageManager` re-renders the
system prompt on every call to `to_llm_messages()`, so time and the daily
memory note stay current across a long-running turn loop rather than being
frozen at `Agent` construction.

`resolve_workspace_root()` resolves the workspace directory from
`CARA_WORKSPACE_ROOT`, then the configured `agent.config.workspace.root`,
defaulting to `~/.cara/workspace` — see the [repo
root README](../README.md#workspace-and-docker-binds) for the expected
layout.

## Tools

Tools are registered on an `agenttoolkit.Tools` instance via
`@tools.action(description=..., params=...)`. Dependencies are declared as
`Inject[SomeType]` parameters and resolved by `agenttoolkit`'s DI container;
`available_when=...` predicates conditionally expose a tool to the model —
for example, model-switch tools only appear when alternatives are configured,
reasoning controls only appear when supported levels are registered, and
volume tools only appear when a `VolumeControl` was injected:

```python
from agenttoolkit import Inject, Tools
from pydantic import Field
from agent.tools.params import ToolParams

class SwitchModelParams(ToolParams):
    name: str = Field(description="Name of the model to switch to, exactly as listed.")

def register_model_control_tools(tools: Tools) -> None:
    @tools.action(description="Validate and switch the active model.", params=SwitchModelParams)
    async def switch_model(params: SwitchModelParams, models: Inject[ModelSwitch]) -> str:
        await models.switch(params.name)
        return f"Smoke test passed. Switched to {params.name}."
```

| Module | Tools |
| --- | --- |
| `actions/filesystem.py` | `list_files`, `glob`, `grep`, `read_file`, `write_file`, `edit_file` — backed by `agenttoolkit.builtins.LocalWorkspace`. |
| `actions/shell.py` | `shell` — runs inside the Docker sandbox via `CommandRunner`. |
| `actions/weather.py` | `weather_report` (now/today/tomorrow/multi-day). |
| `actions/web_search.py` | `web_search`, backed by Tavily. |
| `actions/skills.py` | `load_skill` — loads a skill's full instructions on demand. |
| `actions/model_control.py` | Inspect and smoke-test model/reasoning configuration, then switch atomically; failed candidates leave the active configuration untouched. |
| `actions/volume.py` | `get_volume`, `set_volume` — only when a `VolumeControl` is injected. |
| `actions/memory.py` | `recall` — currently a disabled placeholder pending a `retrieval.TextIndex` backend. |

Weather, location, and search live behind ABCs in `tools/handler/ports.py`
(`Weather`, `LocationLookup`, `WebSearch`), with default adapters
(`OpenMeteoWeather`, `IpLocationLookup`, `TavilyWebSearch`) wired in by
`build_tools()`. Pass `injected_dependencies=(...)` to swap any of them.

`ToolError`, raised from within a tool, is caught by `ToolResultMiddleware`
and converted into a `ToolFailure(str)` result the model can see and react to,
rather than crashing the turn. A fixed set of expected exceptions
(`ValidationError`, `CommandError`, `WorkspaceError`, `FileNotFoundError`, and
similar) get the same treatment; anything else is logged with a full
traceback and re-raised.

## Sandbox

`SandboxDefinition` (`sandbox/config.py`) is a pydantic model validated from
the `agent.config.sandbox` section of `gateway.yaml`, describing the Docker
image, shell, resource limits (memory, PIDs, CPUs), network access, and bind
mounts. `sandbox/factory.py` translates it into an
`agenttoolkit.builtins.DockerSandbox` — `agent` itself defines no sandbox
mechanics, only configuration and translation; the actual jailing,
capability-dropping, and resource limiting live in `mm-agenttoolkit`. See the
[repo root README](../README.md#tool-safety) for the full safety model.

`AgentTools` (`tools/factory.py`) owns the sandbox's lifecycle: `prepare()`
opens it and `aclose()` closes it, called by `Agent.prepare_turn()` /
`finish_turn()`.

## Gateway plugin adapter

```toml
[project.entry-points."cara.agent_plugins"]
cara = "agent.plugin:create_plugin"
```

`agent.plugin` is the sole integration point with the outer Gateway process,
speaking only the [`agent_plugin_api`](../agent_plugin_api) contract:

- `_CaraAgentPlugin.create(config, context)` validates `config` against a
  frozen, `extra="forbid"` `_CaraAgentSettings` (`models`, `workspace`,
  `sandbox`, `system_prompt`) — an unknown config key from `gateway.yaml`
  fails fast at startup.
- `_CaraAgentRunner.run(request)` loads prior turns via
  `AgentSessionReader.context_for_turn(...)`, replays them into `llmify`
  messages, builds a fresh `Agent` (Codex `ChatModel` via
  [`llm`](../llm), `ModelSwitch`, `build_tools(...)`, and
  `Skills.from_dir(workspace/skills)` if present), and maps every internal
  `AgentEvent` to its `agent_plugin_api` counterpart
  (`TextDelta`→`ChatDelta`, `TurnCompleted`→`ChatCompleted`,
  `ToolStarted`→`ToolCallStarted`, `ToolCompleted`→`ToolCallCompleted`).
- `agent.interrupt()` always runs in a `finally`, and `_CaraAgentRunner`
  tracks every active `Agent` so `close()` can interrupt all of them on
  Gateway shutdown.

This is the boundary that keeps `agent` runnable and testable standalone,
while letting the Gateway treat it as an interchangeable, installable plugin.
