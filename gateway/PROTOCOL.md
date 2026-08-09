# Cara Gateway Protocol v0

The protocol separates commands from events:

- clients send commands to the gateway;
- the gateway emits immutable events;
- `session_id` identifies a conversation and `call_id` identifies one tool
  invocation.

## Transport

Connect to `WS /v1/ws/{client_id}` and exchange JSON objects. A successful
`session.create`, `session.get`, or `chat.send` command subscribes that connection
to the session. All subscribed clients receive the session's later turn, chat, and
tool events.

The HTTP endpoints `POST /v1/sessions` and `GET /v1/sessions/{session_id}` are
provided for simple lifecycle and inspection use. Streaming remains on the
WebSocket. The version prefix is applied centrally when the API router is mounted.

## Commands

The minimal command set is:

| Type             | Required routing           | Payload                     |
| ---------------- | -------------------------- | --------------------------- |
| `session.create` | `request_id`               | optional `metadata`         |
| `session.get`    | `request_id`, `session_id` | none                        |
| `chat.send`      | `request_id`, `session_id` | `text`, optional `metadata` |
| `chat.cancel`    | `request_id`, `session_id` | none                        |

Example:

```json
{
  "type": "chat.send",
  "request_id": "req_123",
  "session_id": "0b1d3b0e-6e8b-4c1a-9c2a-1f6a2b7c9d4e",
  "payload": {
    "text": "Mach das Licht an",
    "metadata": { "input": "terminal" }
  }
}
```

Every valid command first produces a client-scoped `command.accepted` event.
Invalid commands produce `command.rejected`, with a stable error `code` and a
human-readable `message`.

## Event envelope

Every event uses one envelope. Fields without a value are omitted on the wire.

```json
{
  "type": "chat.delta",
  "event_id": "b3f0a6e2-1c9e-4d3a-8b6f-2e7a5c1d9f30",
  "timestamp": "2026-08-09T08:45:00Z",
  "session_id": "0b1d3b0e-6e8b-4c1a-9c2a-1f6a2b7c9d4e",
  "sequence": 2,
  "metadata": {},
  "data": { "text": "Hallo" }
}
```

`event_id` and `session_id` are UUIDs. `event_id` is globally unique.
`sequence` is monotonically increasing within a turn and can be used
to order its events. `metadata` is for tracing and adapter context;
event-specific values belong in `data`.

## Events

The minimal lifecycle is:

```text
command.accepted
turn.started
chat.delta                 (zero or more)
tool_call.started          (zero or more, paired by call_id)
tool_call.completed
chat.completed
turn.completed | turn.failed | turn.cancelled
```

Payloads:

| Type                                | `data`                                               |
| ----------------------------------- | ---------------------------------------------------- |
| `chat.delta`                        | `text`                                               |
| `chat.completed`                    | `text`, `finish_reason`                              |
| `tool_call.started`                 | `name`, `arguments`; envelope has `call_id`          |
| `tool_call.completed`               | `name`, `result`, `is_error`; envelope has `call_id` |
| `turn.completed` / `turn.cancelled` | empty                                                |
| `turn.failed`                       | `code`, `message`                                    |

Session lifecycle commands additionally emit `session.created` or the
client-scoped `session.snapshot`.

## Deliberate v0 limits

This version persists sessions and their complete conversation history in SQLite
through SQLModel. Active turns and subscriptions remain in memory. Configure the
database with `DATABASE_URL`; the default is
`sqlite+aiosqlite:///./gateway.sqlite3`. It has no authentication, durable event
log, reconnect replay, command idempotency, or multi-process fanout. Those
concerns can be added behind the application ports without changing the wire
format. The included agent adapter echoes input only so that the complete
protocol can run before the real Cara agent adapter is connected.
