# gateway-rpc-client

Fully typed Python client for the Cara Gateway JSON-RPC 2.0 WebSocket and its
bidirectional `voice.media` binary stream.
Resources such as sessions, automations, and alarms live in
[`gateway-rest-client`](../gateway_rest_client); see
[docs/gateway-transport.md](../../docs/gateway-transport.md).

`pyrpckit` 0.6.0 generates the models, namespace clients, WebSocket transports,
and internal runtime from `gateway/schema/gateway.openrpc.json`.
`gateway-server`'s `cara-gateway-rpc-client-generate` command adds the bearer-token
connection helper. The package does not import `gateway-server`.

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
endpoints (`http` to `ws`, `https` to `wss`).

## Regenerating

```bash
./scripts/codegen/generate_gateway_clients.sh
```

All Python files under `src/gateway_rpc_client/` are generated; do not edit
them by hand. CI fails when the checked-in output drifts from the schema.
