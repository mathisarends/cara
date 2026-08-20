# Cara Gateway Python client

This package is generated from `gateway/schema/gateway.openrpc.json`. It has no
import, build, or runtime dependency on the `gateway` workspace package.

Generate the checked-in client after changing the protocol:

```text
uv run cara-gateway-schema
uv run cara-gateway-client-generate gateway/schema/gateway.openrpc.json
```

Use the namespaced, fully typed API:

```python
from gateway_client import GatewayClient

async with await GatewayClient.connect("ws://127.0.0.1:8000/v1/gateway") as client:
    session = await client.session.create(metadata={"app": "ios"})
    await client.session.subscribe(session_id=session.id)
    await client.turn.start(session_id=session.id, message="Hallo")

    async for notification in client.notifications():
        match notification.params:
            case event if event.type == "chat.delta":
                print(event.text, end="")
```

The generated `models.py` contains the wire models and discriminated event
union. `client.py` contains one API namespace per OpenRPC method prefix. Run the
generator with `--check` in CI to detect stale generated sources.
