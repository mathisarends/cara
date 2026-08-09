# gateway-client

Typed async client for the Cara Gateway.

`src/gateway_client/models.py` mirrors `openapi.json`, a snapshot of the spec
served at `/openapi.json`. When the gateway API changes, refresh the snapshot and
regenerate the models — everything else in the package is hand-written client
logic and stays put.

```python
from gateway_client import ChatCompletedEvent, ChatDeltaEvent, GatewayClient

async with GatewayClient("http://127.0.0.1:8000") as client:
    created = await client.create_session({"channel": "terminal"})
    session = client.session(created.id)

    async with session.events() as events:
        await session.send("Hello")
        async for event in events:
            match event:
                case ChatDeltaEvent(data=data):
                    print(data.text, end="", flush=True)
                case ChatCompletedEvent():
                    break
```

Open the event stream before starting a turn: the gateway does not replay events
emitted while no client was subscribed.
