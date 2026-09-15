# gateway-rest-client

Fully typed async Python client for the Cara Gateway REST resources: sessions,
automations, and alarms. `httpxgen` generates it from
`gateway/schema/openapi.json`. The connection-bound part of the API (turns,
subscriptions, events) lives in [`gateway-rpc-client`](../gateway_rpc_client);
see [docs/gateway-transport.md](../../docs/gateway-transport.md).

```python
import httpx2

from gateway_rest_client import GatewayRestClient, OpenSessionRequest, SessionChannel

async with httpx2.AsyncClient() as http:
    client = GatewayRestClient(
        http,
        "http://127.0.0.1:8000",
        credentials={"GatewayToken": token},
    )
    session = await client.open_session(
        OpenSessionRequest(channel=SessionChannel(name="cli"))
    )
```

The client borrows the HTTP client and never closes it. Failures raise
`TransportError` (unreachable), `ApiError` (error status with the parsed
problem in `detail`), or the other `ClientError` subclasses.

## Regenerating

```bash
./scripts/codegen/generate_gateway_clients.sh
```

All Python files under `src/gateway_rest_client/` are generated; do not edit
them by hand. CI fails when the checked-in output drifts from the schema.
