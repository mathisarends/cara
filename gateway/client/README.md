# gateway-client

Fully typed Python client for the Cara Gateway JSON-RPC 2.0 WebSocket API.
`pyrpckit` 0.4.0 generates the models, namespace clients, WebSocket transport,
and internal runtime from `gateway/server/schema/gateway.openrpc.json`.
`gateway-codegen` adds the Gateway bearer-token connection helper.
The package does not import `gateway-server`.

```python
from gateway_client import connect_gateway
from gateway_client.models import SessionChannel

client = await connect_gateway(url, token=token)
async with client:
    session = await client.session.open(channel=SessionChannel(name="cli"))
    await client.turn.start(session_id=session.id, message="Hallo")
    async for event in client.session.event():
        ...
```

Methods are grouped by RPC prefix (`client.session.*`, `client.turn.*`), take
keyword arguments, and return parsed Pydantic models. The client exports
`RpcRemoteError`, `RpcTransportError`, and the other generated client errors.

## Regenerating

```bash
uv run --package gateway-server cara-gateway-schema
uv run --package gateway-codegen cara-gateway-client-generate \
  gateway/server/schema/gateway.openrpc.json
```

All Python files under `src/gateway_client/` are generated; do not edit them
by hand. `--check` validates the checked-in output without writing it.
