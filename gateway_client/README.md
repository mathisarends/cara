# gateway-client

Typed async client for the Cara Gateway.

`src/gateway_client/models.py` and `src/gateway_client/operations.py` are
generated from `openapi.json`, a snapshot of the spec served at `/openapi.json`.
Hand-written are only the parts the spec cannot describe: `transport.py`
(connection, error mapping), `errors.py`, `events.py` (the WebSocket route is not
part of an OpenAPI document) and `client.py`, which ties them together.

```sh
./scripts/generate_client.sh                              # from the snapshot
./scripts/generate_client.sh --url http://127.0.0.1:8000  # refresh it first
```

Operations are grouped into one namespace per OpenAPI tag, one method per
`operationId`:

```python
from gateway_client import (
    ChatCompletedEvent,
    ChatDeltaEvent,
    ChatRequest,
    GatewayClient,
    SessionCreateRequest,
)

async with GatewayClient("http://127.0.0.1:8000") as client:
    await client.system.get_gateway_health()
    session = await client.sessions.create_session(SessionCreateRequest())

    async with client.event_stream(session.id) as events:
        await client.sessions.start_chat(session.id, ChatRequest(text="Hello"))
        async for event in events:
            match event:
                case ChatDeltaEvent(data=data):
                    print(data.text, end="", flush=True)
                case ChatCompletedEvent():
                    break
```

Open the event stream before starting a turn: the gateway does not replay events
emitted while no client was subscribed.

The generator covers the subset of OpenAPI 3.1 the gateway emits and fails on
anything outside it rather than guessing — inline schemas, non-path parameters
and non-JSON payloads raise `UnsupportedSchemaError`. It drops field
descriptions and does not translate `additionalProperties: false` into
`extra="forbid"`, so the client keeps parsing responses after the server adds a
field.
