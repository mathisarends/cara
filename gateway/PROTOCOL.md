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
`subscription.subscribe`, `subscription.unsubscribe`, `turn.start`,
`turn.steer`, and `turn.cancel`.
Events arrive as `session.event` notifications after an explicit subscription.

`turn.steer` hands a message to the turn that is already running. The agent
picks it up at its next tool-call boundary and only then does it enter the
transcript, announced by a `turn.steered` event; a message that arrives after
the last boundary of a turn never reaches the model, so a client that wants it
delivered has to resend it as a new turn.

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
turn.steered
turn.completed | turn.failed | turn.cancelled
```

## Protocol source and generated specifications

RPC methods are free functions registered on a feature-owned `RpcModule`.
Their Pydantic parameter and result annotations define the wire contract;
services are resolved with `Inject`:

```python
from pyrpckit import Inject, RpcModule

conversation_module = RpcModule()

@conversation_module.method("session.get", errors=(ResourceNotFoundError,))
async def get_session(
    params: SessionParams,
    handler: Inject[ConversationRpcMethods],
) -> SessionSnapshotResponse:
    return await handler.get_session(params)
```

Conversation event payloads are Pydantic models with discriminated `type`
fields. `events.py` registers the `session.event` async source on another
`RpcModule`. The Gateway channel includes the feature and event modules.

Generate the checked-in contract and client with:

```bash
uv run --package gateway-server cara-gateway-schema
uv run --package gateway-codegen cara-gateway-client-generate \
  gateway/schema/gateway.openrpc.json
```

`schema/gateway.openrpc.json` contains method parameters, results, errors,
notifications, and notification payload types.
