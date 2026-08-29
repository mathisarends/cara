# Cara gateway protocol

Cara exposes one long-lived JSON-RPC 2.0 WebSocket:

```text
ws://127.0.0.1:8000/v1/gateway
```

The WebSocket upgrade must include the shared Gateway credential:

```http
Authorization: Bearer <CARA_GATEWAY_TOKEN>
```

The Gateway rejects missing or invalid credentials before accepting the
protocol connection.

Commands, correlated responses, and subscribed session events share that
connection. The connection lifecycle lives at the gateway presentation boundary;
each feature owns its Pydantic wire models and request handling.

Available methods are `session.create`, `session.open`, `session.get`,
`subscription.subscribe`, `subscription.unsubscribe`, `turn.start`, and `turn.cancel`.
Events arrive as `session.event` notifications after an explicit subscription.

`session.create` always creates a fresh session. `session.open` returns the most
recent session with the same channel identity or creates one when none exists.
Channel identity currently consists of `name` plus an optional `account_id`;
the gateway owns the resulting opaque session UUID.

Example:

```json
{"jsonrpc":"2.0","id":1,"method":"session.open","params":{"channel":{"name":"voice","account_id":"local"}}}
{"jsonrpc":"2.0","id":2,"method":"subscription.subscribe","params":{"session_id":"<uuid>"}}
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
from pyrpckit import method

@method(
    "session.get",
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
from pyrpckit import event

@event
class ChatDelta(EventBase):
    type: Literal["chat.delta"] = "chat.delta"
    text: str
```

Decorators only attach metadata. They do not mutate a global registry. Each
feature explicitly creates its protocol definition with `pyrpckit.feature(...)`,
and the gateway composes those definitions. The same definitions drive
runtime dispatch and specification generation — all via
`pyrpckit`, the transport-agnostic JSON-RPC library gateway is
built on.

Generate the checked-in artifacts with:

```text
uv run cara-gateway-schema
```

Outputs:

- `schema/gateway.openrpc.json` maps every method to params, result, and errors.
- `schema/gateway.schema.json` contains the complete JSON Schema model graph.
- `x-rpc-notifications` maps notification names to their payload unions.
- `x-rpc-events` maps every decorated event name to its concrete payload.
