# Support server-to-client requests (callbacks)

## Summary

pyrpckit currently supports two directions on a WebSocket endpoint:

- **`@channel.method`**: the client calls the server, and the server responds.
- **`@channel.event`**: the server sends a notification to the client, and nothing comes back. The schema describes events under `x-rpc-notifications`.

What is missing is **server → client requests**: the server calls something the connected client implements and awaits its result or error. I'd like to propose adding this as **callbacks**:

```python
room_channel.method(...)    # client calls server, server responds
room_channel.event(...)     # server sends, no response
room_channel.callback(...)  # server calls client, client responds
```

## Motivation

In a home-assistant setup, each room runs a small client process that owns local hardware (speaker, lights, media player). The client dials out to the server over one WebSocket, which also gives the server the online status for free. The server then needs to send commands to a specific room and know the outcome.

With only events, every application has to build the same workaround by hand:

1. Send an event with a self-generated `command_id`.
2. Have the client report back through a separate method (`command.completed` / `command.failed`).
3. Correlate the two on the server, apply a timeout, and fail pending commands on disconnect.

That is request/response correlation, which is exactly what the RPC layer already does in the other direction. The alternative, having the server call a REST endpoint on the client, inverts the connection direction: clients must become reachable, need their own auth, and lose connection-bound presence.

## Prior art and spec compatibility

- **JSON-RPC 2.0** defines client and server as roles per message, not per connection: *"One implementation of this specification could easily fill both of those roles, even at the same time, to other different clients or the same client."* LSP relies on this heavily (e.g. `workspace/applyEdit`, `window/showMessageRequest`).
- **OpenRPC** describes the methods a single service exposes and has no notion of direction. It doesn't cover server notifications either, which pyrpckit already describes through the `x-rpc-notifications` extension. Callbacks would follow the same pattern with a new specification extension, `x-rpc-callbacks`.
- **OpenAPI** uses the same term for the same concept: `callbacks` are requests the API provider sends to the consumer, described in the provider's own API document. Here, likewise, the server's contract declares what the client must answer.

## Proposed design

### Declaration

A callback is a typed declaration, not a decorated function, because the server has nothing to implement:

```python
room_channel = RpcChannel("room", namespace="room")

media_play = room_channel.callback(
    "media.play",
    params=MediaPlayParams,
    result=MediaPlayResult,
    raises=(MediaUnavailableError,),
    summary="Play a media URI on the room's speaker.",
)
```

`callback(...)` returns an `RpcCallback[P, R]` that carries the wire name, the params and result models, and the declared errors. Name collisions with methods, events, and streams in the same namespace are rejected, just as they are today.

### Server side: calling a callback

The server needs a handle to the connection it wants to call. `RpcPeer` should be injectable wherever connection-scoped dependencies are injectable today, so an application can keep its own registry (e.g. room id → peer) and call callbacks from anywhere:

```python
@room_channel.method("hello")
async def hello(
    params: HelloParams,
    peer: Inject[RpcPeer],
    rooms: Inject[RoomConnections],
) -> None:
    rooms.attach(params.room_id, peer)


result = await peer.call(media_play, MediaPlayParams(uri=uri), timeout=5.0)
```

`RpcPeer.call` semantics:

- It allocates request ids from a server-side id space that can't collide with the ids the client uses for its own requests.
- It validates params against the declared model and the response against the declared result model.
- It raises the declared typed errors for matching error codes, and a generic RPC error otherwise.
- It raises a dedicated timeout error when `timeout` elapses and drops the late response.
- When the connection closes, all pending calls fail with a dedicated disconnect error.
- It respects the existing limits (max concurrency, message size) in the outgoing direction.

### Client side: implementing callbacks

The generated client exposes an ABC per namespace that the application implements and registers on connect:

```python
class RoomHandlers(RoomCallbacks):  # generated ABC
    async def media_play(self, params: MediaPlayParams) -> MediaPlayResult: ...


async with GatewayRpcClient.connect(url, token=token, callbacks=RoomHandlers()) as client:
    ...
```

The generated client:

- routes incoming request frames (frames with `id` and `method`) to the registered handler, alongside the existing handling of notifications and responses
- answers with a result or an error envelope and maps declared exceptions to their error codes
- answers `-32601 Method not found` when the server calls a callback that has no registered handler
- runs handlers concurrently, so a slow handler doesn't block responses to the client's own requests

### Schema

A new top-level extension next to `x-rpc-notifications`:

```json
"x-rpc-callbacks": [
  {
    "name": "room.media.play",
    "summary": "Play a media URI on the room's speaker.",
    "params": [...],
    "result": {...},
    "errors": [...],
    "x-rpc-params-schema": {...}
  }
]
```

Entries use the same shape as regular `methods`, so the existing schema and codegen machinery can be reused. Codegen reads the extension and generates the callback ABC plus its models.

## Open questions

- **Id space**: prefix numeric ids, or always use string ids for server-originated requests?
- **Connection handle**: expose `RpcPeer` only through injection, or also on the observer contexts (`connection_opened` / `connection_closed`) so registries can attach and detach there?
- **Partial implementation**: must a client implement every callback of a namespace (ABC with abstract methods), or may it opt into a subset and let the rest answer `-32601`?
- **Observability**: extend the observer with `callback_started` / `callback_finished`?

## Acceptance criteria

- `channel.callback(...)` declares a typed callback. Name collisions with methods, events, and streams are rejected.
- The server can invoke a callback through an injected `RpcPeer`, with timeout, typed errors, and disconnect handling.
- The OpenRPC document contains `x-rpc-callbacks`, and the codegen generates a callback ABC for the Python client.
- The Python client dispatches incoming requests to registered handlers and responds correctly, including `-32601` for unknown callbacks.
- `RpcTestClient` can register callback handlers, so both directions are testable without a real socket.
