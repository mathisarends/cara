# agent

Cara's tool-calling loop, prompt assembly, model switching, and trusted tool
catalog. The Gateway composes this library directly and injects its workspace,
command runner, reminders, and MCP tools.

```python
from agent import Agent, AgentFactory, AgentSettings
```

Docker lifecycle and network transports live outside this package. See the
[architecture vision](../AGENT_RUNTIME_ARCHITECTURE_VISION.md).
