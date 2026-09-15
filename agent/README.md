# agent

Cara's generic tool-calling loop, prompt assembly, model switching, tool
extension API, and middleware. Concrete tools and integrations belong to the
embedding host; Cara's Gateway provides its own catalog.

```python
from agent import Agent, AgentFactory, AgentSettings
```

`AgentFactory` requires an explicit `Workspace` and `CommandRunner`; the package
does not create a local execution fallback. Workspace configuration, sandbox
lifecycle, tool selection, tool dependencies, and network transports belong to
the embedding host.
