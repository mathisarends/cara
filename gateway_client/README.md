# Cara Gateway Python client

`gateway_client` is a fully typed, code-generated Python client for the Cara
Gateway's JSON-RPC 2.0 WebSocket API. It is generated from
`gateway/schema/gateway.openrpc.json` and has no import, build, or runtime
dependency on the `gateway` workspace package — only `pydantic` and
`websockets`. Any process that can reach the Gateway over WebSocket — the
[`cli`](../cli) client, the voice pipeline, or a future channel — can depend on
this package alone.

## Table of contents

- [Quickstart](#quickstart)
- [Regenerating the client](#regenerating-the-client)
- [What gets generated](#what-gets-generated)
- [Transport and error handling](#transport-and-error-handling)
- [Package layout](#package-layout)

## Quickstart

```python
from gateway_client import GatewayClient

async with await GatewayClient.connect("ws://127.0.0.1:8000/v1/gateway") as client:
    session = await client.session.open(channel={"name": "cli"}, metadata={"app": "ios"})
    await client.session.subscribe(session_id=session.id)
    await client.turn.start(session_id=session.id, message="Hallo")

    async for notification in client.notifications():
        match notification.params:
            case event if event.type == "chat.delta":
                print(event.text, end="")
            case event if event.type == "turn.completed":
                break
```

Every RPC method is namespaced on the client by its method prefix
(`client.session.*`, `client.turn.*`), takes keyword-only parameters, and
returns a parsed Pydantic model — never a raw `dict`. `client.notifications()`
streams every server-pushed event (chat deltas, tool calls, turn lifecycle) as
a validated `SessionEventNotification`.

## Regenerating the client

Whenever the Gateway's RPC surface changes, regenerate the schema and the
client together, from the workspace root:

```bash
uv run cara-gateway-schema
uv run cara-gateway-client-generate gateway/schema/gateway.openrpc.json
```

The first command introspects the Gateway's RPC method registry and writes
`gateway/schema/gateway.openrpc.json` (see [`gateway`](../gateway) for how
that introspection works). The second reads that file and regenerates every
file under `gateway_client/src/gateway_client/` listed below.

Run the generator with `--check` in CI to fail the build when the checked-in
client has drifted from the schema:

```bash
uv run cara-gateway-client-generate gateway/schema/gateway.openrpc.json --check
```

`--check` writes nothing; it exits non-zero the moment any generated file
would differ from what is on disk, which is exactly what catches an OpenRPC
change that was never followed by a regeneration.

## What gets generated

`gateway_client/src/gateway_client/codegen.py` turns one OpenRPC document into
four kinds of source, all carrying the same "do not edit" header:

| Output | Generated from |
| --- | --- |
| `models.py` | Every schema under `components.schemas`: enums (`StrEnum`/`IntEnum`), Pydantic models (`GatewayModel` subclasses with `extra="forbid"` where the schema itself forbids additional properties), discriminated unions built from OpenRPC `discriminator` blocks (e.g. `SessionEvent`, the `type`-discriminated union all chat/tool/turn events belong to), and an `RpcMethod` enum with one member per RPC method name. |
| `client.py` | The top-level `GatewayClient`: one attribute per namespace, `connect()`, `notifications()` (a `TypeAdapter(SessionEventNotification)`-validated stream), and `close()`/async context-manager support. |
| `namespaces/<name>.py` | One class per method-name prefix (`session.*` → `SessionClient`, `turn.*` → `TurnsClient`). Each RPC method becomes one `async def` that builds its params model, calls `RpcTransport.request()`, and validates the result. |
| `namespaces/__init__.py` | Re-exports every namespace class. |

Because models and namespace clients are both derived mechanically from the
same schema, adding a Gateway RPC method or changing a wire model never
requires touching this package by hand — only running the two commands above.

## Transport and error handling

```python
from gateway_client import GatewayClientError, GatewayRpcError, GatewayTransportError, RpcTransport
```

`RpcTransport` is the one hand-written seam in the package — a small
`Protocol` (`request`, `notifications`, `close`) that `WebSocketTransport`
implements over `websockets`. Every namespace method calls through it, so a
test can swap in a fake transport without touching generated code.

`WebSocketTransport` frames each call as a JSON-RPC 2.0 request with an
incrementing integer `id`, resolves it against a pending `asyncio.Future` when
the matching response arrives, and routes every message *without* an `id`
into the notification queue instead — that is the distinction between an RPC
response and a server-pushed event on this one WebSocket connection.

| Error | Raised when |
| --- | --- |
| `GatewayRpcError` | The Gateway responds with a JSON-RPC `error` object; carries `code`, `message`, and optional `data`. |
| `GatewayTransportError` | The WebSocket connection closes or fails while a request is pending or being awaited. |

On disconnect, every still-pending request is failed with a
`GatewayTransportError` and the notification stream ends, so a caller awaiting
either a request or `async for` over `notifications()` observes the drop
instead of hanging.

## Package layout

```text
gateway_client/src/gateway_client/
├── __init__.py       public exports
├── transport.py       RpcTransport protocol + WebSocketTransport (hand-written)
├── errors.py           GatewayClientError, GatewayRpcError, GatewayTransportError (hand-written)
├── codegen.py           the generator: OpenRPC -> models.py / client.py / namespaces/* (hand-written)
├── client.py             GatewayClient (generated)
├── models.py             wire models, enums, discriminated unions (generated)
└── namespaces/
    ├── __init__.py       namespace re-exports (generated)
    ├── session.py         SessionClient: create, open, get, subscribe, unsubscribe (generated)
    └── turn.py             TurnsClient: start, cancel (generated)
```
