# agent

Cara's model-agnostic conversational agent core: the stateful tool-calling
loop, system-prompt assembly, and the application-specific tool catalog
(filesystem, shell/sandbox, weather, web search, volume, skills, model
switching, reminders).

## Public API

```python
from agent import Agent, AgentFactory, AgentSettings, ModelSettings, ModelSwitch, SystemPrompt, WorkspaceSettings
```

Everything else is imported directly from its module (`agent.tools`,
`agent.sandbox`, `agent.events`, `agent.messages`, `agent.workspace`,
`agent.plugin`).

## Layout

```text
src/agent/
├── agent.py          Agent: async tool-calling loop, streams AgentEvents
├── factory.py         AgentFactory: composes workspace/models/skills/tools into an Agent
├── configuration.py   AgentSettings, WorkspaceSettings
├── dependencies.py    configured DI providers and resolved AgentComponents
├── events.py           TextDelta, ToolStarted, ToolCompleted, TurnCompleted
├── messages.py       MessageManager: history + system prompt injection
├── models.py          ModelSwitch: named ChatModel registry
├── plugin/             cara.agent_plugins entry point (Gateway adapter)
├── prompt/              system prompt composition
├── sandbox/             SandboxDefinition -> agenttoolkit DockerSandbox
└── tools/                tool catalog (actions/, handler/ ports+adapters)
```

## Dependencies

- `mm-agenttoolkit` — tool registration, DI, schema generation, skills,
  workspace access, and Docker sandboxing. This package only defines *what*
  tools Cara has and *how* its loop/prompt are built.
- [`gateway-server`](../gateway/server) discovers and drives this package as
  a plugin via the `cara.agent_plugins` entry point
  (`agent.plugin:create_plugin`), speaking only the
  [`agent_plugin_api`](../gateway/plugin_api) contract — the integration
  boundary the Gateway drives the agent through.
- [`gateway-client`](../gateway/client) is how the reminder tools call back
  into the Gateway's automation API. They are bound to the session and turn
  the agent is running in, and stay hidden from the model unless
  `CARA_GATEWAY_TOKEN` is set.

See the [repo root README](../README.md) for workspace layout and the tool
safety model.
