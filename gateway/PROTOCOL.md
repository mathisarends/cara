# Cara gateway protocol

Cara exposes one long-lived JSON-RPC 2.0 WebSocket:

```text
ws://127.0.0.1:8000/v1/gateway
```

Commands, correlated responses, and subscribed session events share that
connection. The connection lifecycle lives at the gateway presentation boundary;
each feature owns its Pydantic wire models and request handling.

Available methods are `session.create`, `session.get`, `session.subscribe`,
`session.unsubscribe`, `turn.start`, and `turn.cancel`. Events arrive as
`session.event` notifications after an explicit subscription.

Example:

```json
{"jsonrpc":"2.0","id":1,"method":"session.create"}
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
