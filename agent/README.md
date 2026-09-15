# agent

Cara's tool-calling loop, prompt assembly, model switching, and trusted tool
catalog. The Gateway composes this library directly and injects its workspace,
command runner, reminders, and MCP tools.

```python
from agent import Agent, AgentFactory, AgentSettings
```

`AgentFactory` requires an explicit `Workspace` and `CommandRunner`; the package
does not create a local execution fallback. Workspace configuration, sandbox
lifecycle, and network transports belong to the embedding host.
