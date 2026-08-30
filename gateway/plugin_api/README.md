# agent-plugin-api

Dependency boundary between the Cara Gateway and an installed agent plugin.
Contains only immutable request/context models, streamed agent events, and
structural protocols — no FastAPI, Dishka, SQLModel, or Gateway
implementation code, and no runtime dependencies of its own.

The Gateway owns sessions and transcripts. A plugin's `AgentRunner` receives
only the current turn as an `AgentRunRequest`; earlier history comes through
the read-only `AgentSessionReader` on `AgentPluginContext`. A plugin never
gets write access to session state — it streams `AgentEvent`s back and the
Gateway persists them.

```python
class AgentRunner(Protocol):
    def run(self, request: AgentRunRequest) -> AsyncIterator[AgentEvent]: ...
    async def steer(self, session: AgentSessionRef, text: str) -> None: ...
    async def close(self) -> None: ...

class AgentPlugin(Protocol):
    api_version: int
    def create(self, config: Mapping[str, Any], context: AgentPluginContext) -> AgentRunner: ...
```

Registered via the `cara.agent_plugins` entry-point group; the Gateway
validates the loaded object against these `@runtime_checkable` protocols and
checks `api_version` against `AGENT_PLUGIN_API_VERSION` before invoking it —
see [`gateway-server`](../server#agent-plugin-system) for the loading
sequence.

Key types: `AgentChannelRef`, `AgentSessionRef`, `AgentRunRequest`,
`AgentContext`/`AgentContextEntry`, `AgentToolCall(Sequence)`; events
`ChatDelta`, `ChatCompleted`, `ToolCallStarted`, `ToolCallCompleted`,
`TurnSteered`.

`steer` queues text for a turn that is still running; the runner decides where
it is safe to apply and reports that back as `TurnSteered`, which is the point
at which the Gateway writes the message into the transcript. A steer for a
turn that has already ended is dropped, not an error.

## Dependencies

None. Depended on by [`gateway-server`](../server) (the loader/contract) and
by any installed plugin, e.g. [`agent`](../../agent).
