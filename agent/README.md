# agent

Cara's generic tool-calling loop, prompt assembly, tool extension API, and
middleware. Concrete models, tools, and integrations belong to the embedding
host; Cara's Gateway provides its own catalog.

```python
from agent import Agent, AgentFactory, AgentSettings
```

`AgentFactory` requires an explicit model factory, `Workspace`, and
`CommandRunner`; the package does not create local fallbacks. Model and
workspace configuration, sandbox lifecycle, tool selection, tool dependencies,
and network transports belong to the embedding host.
