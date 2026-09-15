# gateway-rpc-client

Fully typed Python client for the Cara Gateway JSON-RPC 2.0 WebSocket: the
connection-bound part of the API (`subscription.*`, `turn.*`, `session.event`).
Resources such as sessions, automations, and alarms live in
[`gateway-rest-client`](../gateway_rest_client); see
[docs/gateway-transport.md](../../docs/gateway-transport.md).

`pyrpckit` 0.4.0 generates the models, namespace clients, WebSocket transport,
and internal runtime from `gateway/schema/gateway.openrpc.json`.
`gateway-server`'s `cara-gateway-rpc-client-generate` command adds the bearer-token
connection helper. The package does not import `gateway-server`.

```python
from gateway_rpc_client import connect_gateway

client = await connect_gateway("http://127.0.0.1:8000", token=token)
async with client:
    await client.subscription.subscribe(session_id=session_id)
    await client.turn.start(session_id=session_id, message="Hallo")
    async for event in client.session.event():
        ...
```

`connect_gateway` takes the Gateway base URL and derives the socket endpoint
(`http` → `ws`, `https` → `wss`, path `/v1/gateway`).

## Regenerating

```bash
./scripts/codegen/generate_gateway_clients.sh
```

All Python files under `src/gateway_rpc_client/` are generated; do not edit
them by hand. CI fails when the checked-in output drifts from the schema.
