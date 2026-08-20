# Cara gateway protocol

Cara exposes one long-lived JSON-RPC 2.0 WebSocket:

```text
ws://127.0.0.1:8000/v1/gateway
```

Commands, correlated responses, and subscribed session events share that
connection. The connection lifecycle lives at the gateway presentation boundary;
each feature owns its Pydantic wire models and request handling.

Available methods are `session.create`, `session.open`, `session.get`,
`session.subscribe`, `session.unsubscribe`, `turn.start`, and `turn.cancel`.
Events arrive as `session.event` notifications after an explicit subscription.

`session.create` always creates a fresh session. `session.open` returns the most
recent session with the same channel identity or creates one when none exists.
Channel identity currently consists of `name` plus an optional `account_id`;
the gateway owns the resulting opaque session UUID.

Example:

```json
{"jsonrpc":"2.0","id":1,"method":"session.open","params":{"channel":{"name":"voice","account_id":"local"}}}
{"jsonrpc":"2.0","id":2,"method":"session.subscribe","params":{"session_id":"<uuid>"}}
{"jsonrpc":"2.0","id":3,"method":"turn.start","params":{"session_id":"<uuid>","message":"Hallo"}}
```

Every event is a concrete discriminated model rather than a generic data
envelope. The turn lifecycle is:

```text
turn.started
chat.delta* / chat.completed
tool_call.started / tool_call.completed
turn.completed | turn.failed | turn.cancelled
```

## Protocol source and generated specifications

RPC metadata belongs exclusively to presentation handlers. Parameter and result
types are derived from their annotations:

```python
@rpc.method(
    "session.get",
    summary="Get a conversation session snapshot.",
    errors=(RpcErrorCode.RESOURCE_NOT_FOUND,),
)
async def get_session(
    self,
    params: SessionParams,
) -> SessionSnapshotResponse:
    ...
```

Wire events follow the same rule. Application and domain events remain unaware
of JSON-RPC; a presentation mapper converts them to decorated Pydantic messages:

```python
@rpc.event("chat.delta")
class ChatDelta(EventBase):
    type: Literal["chat.delta"] = "chat.delta"
    text: str
```

Decorators only attach metadata. They do not mutate a global registry. Each
feature explicitly creates its protocol definition with `rpc_feature(...)`, and
the gateway composes those definitions. The same definitions drive runtime
dispatch and specification generation.

Generate the checked-in artifacts with:

```text
uv run cara-gateway-schema
```

Outputs:

- `schema/gateway.openrpc.json` maps every method to params, result, and errors.
- `schema/gateway.schema.json` contains the complete JSON Schema model graph.
- `x-cara-notifications` maps notification names to their payload unions.
- `x-cara-events` maps every decorated event name to its concrete payload.
