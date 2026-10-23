# gateway-rpc-client

Fully typed Python client for the Cara Gateway JSON-RPC 2.0 WebSocket and its
bidirectional `voice.media` binary stream.
Resources such as sessions, automations, and alarms live in
[`gateway-rest-client`](../gateway_rest_client); see
[docs/gateway-transport.md](../../docs/gateway-transport.md).

`fastapi-rpckit` 0.4.0 generates the models, namespace clients, WebSocket transports,
and internal runtime from `gateway/schema/gateway.openrpc.json`.
`gateway-server`'s `cara-gateway-rpc-client-generate` command adds the bearer-token
connection helpers. The SDK bundles its runtime and requires neither
`gateway-server` nor `fastapi-rpckit` in consuming applications.

```python
from gateway_rpc_client import connect_gateway

client = await connect_gateway("http://127.0.0.1:8000", token=token)
async with client:
    await client.subscription.subscribe(session_id=session_id)
    async with client.voice.media(voice_session_id=str(voice_session_id)) as media:
        await media.send(frame)
        async for response in media:
            ...
```

`connect_gateway` takes the Gateway base URL and derives both WebSocket
endpoints (`http` to `ws`, `https` to `wss`). The helpers use `lazy=True` so
room sockets open when first used. A direct `GatewayRpcClient.connect()` call
opens every declared server unless you pass `lazy=True`.

`client.closed` resolves immediately on terminal connection loss; room presence
uses that signal alongside its state-report heartbeat. `GatewayLink` owns room
reconnection and re-registers and replays state on every new connection. SDK
reconnect and method retries stay disabled: conversation subscriptions and media
ownership require application-level recovery, and a lost response does not mean
that a turn command was never executed.

Use `GatewayRpcClient.with_transports(...)` for custom transports. Their
`request` method accepts keyword-only `metadata` for the new trace-context
carrier. Use SDK middleware for instrumentation. The generator formats for the
SDK's declared Python 3.13 minimum so forward references remain valid there.

## Regenerating

```bash
./scripts/codegen/generate_gateway_clients.sh
```

All Python files under `src/gateway_rpc_client/` are generated; do not edit
them by hand. CI fails when the checked-in output drifts from the schema.
