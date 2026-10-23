# Gateway Transport: REST vs. WebSocket RPC

Rule: WebSocket RPC only for state bound to a live connection or an active turn. Everything else (CRUD, session lookup, initial load) is REST.

## WebSocket (`/v1/gateway`, JSON-RPC)

- `subscription.subscribe` / `subscription.unsubscribe`: connection-bound session subscription
- `subscription.subscribe_channel` / `subscription.unsubscribe_channel`: connection-bound channel subscription that survives session rotation
- `turn.start`: result arrives as events on the socket anyway
- `turn.steer` / `turn.cancel`: control a running turn
- `turn.prepare` / `turn.finish`: latency-sensitive agent lifecycle hints during a conversation
- Notification `session.event`
- `voice.turn.start` / `voice.turn.interrupt` / `voice.turn.playback_completed`: control a live voice turn
- Notification `voice.event`: voice lifecycle for subscribed conversation sessions

## Media WebSocket (`/v1/voice-sessions/{id}/media`, binary)

- Full-duplex PCM audio uses fastapi-rpckit's generated bidirectional `voice.media` stream with a compact versioned frame header.
- The authenticated connection is the sole input/output owner of that voice session.
- Audio never passes through JSON-RPC. A turn's input completion is an ordered media frame; the RPCkit end message closes input for the whole media stream.

## Room WebSocket (`/v1/rooms/{room_id}/channel`, JSON-RPC)

- Presence is bound to the authenticated socket lifetime; Uvicorn ping/pong heartbeats detect broken connections.
- Room clients report room state, device status, and volume on this connection.
- A room must exist in `gateway.yml` and register its devices through REST before connecting.
- Room state, device status and volume reports declare idempotency in the contract.
- The room observes the generated SDK's `closed` signal as well as its periodic
  state-report heartbeat. `GatewayLink` owns reconnect, registration and state replay;
  SDK reconnect stays disabled to avoid a second recovery loop.
- All RPC methods are implemented by the Gateway. Future commands to room hardware
  use typed events and explicit result reports; see [room commands](../specs/ROOM_COMMANDS.md).

## REST

- Sessions: `POST /v1/sessions`, `POST /v1/sessions/open`, `GET /v1/sessions/{id}`
- Automations: `/v1/owners/{owner_id}/automations` (CRUD)
- Alarms: `/v1/owners/{owner_id}/alarms` (CRUD, `enabled`, `skip-next`, `snooze`, `dismiss`)
- Voice sessions: `POST /v1/voice-sessions`, list/get/close, and persisted turn snapshots
- Voice recordings: `GET /v1/voice-sessions/{id}/recording` serves every finished turn as one MP3 (`audio/mpeg`); segments live per turn in object storage (`CARA_GATEWAY_STORAGE_*`, MinIO in Compose)
- Rooms: `GET /v1/rooms`, `GET /v1/rooms/{room_id}`, and idempotent `PUT /v1/rooms/{room_id}/registration`
- LLM: `GET /v1/llm/model-options` lists the configured models and reasoning efforts; the active selection is per conversation and changes through the agent's model-control tools
- Future resource features: REST only, no RPC layer
- Every resource router requires `Authorization: Bearer <CARA_GATEWAY_TOKEN>` (`require_token`, OpenAPI scheme `GatewayToken`); only health is open

## Contracts and clients

| Contract | Schema | Generated client |
| --- | --- | --- |
| REST | `gateway/schema/openapi.json` | `generated/gateway_rest_client` (`GatewayRestClient`, httpxgen) |
| RPC and binary stream | `gateway/schema/gateway.openrpc.json` | `generated/gateway_rpc_client` (`GatewayRpcClient`, fastapi-rpckit) |

- Regenerate both: `scripts/codegen/generate_gateway_clients.sh`
- CI (`gateway-schema-drift.yml`) reruns it and fails on any diff or untracked file
- Clients configure one base URL (`http://host:port`); `connect_gateway` derives the JSON-RPC and media `ws(s)` URLs
- REST discriminated-union members declare their tag (`kind`/`type`) without a default: httpxgen rejects a discriminator that is both required and defaulted

## Canon integration

- Gateway, Room and Sandbox Manager compose their features with `fastapi-canon`
  0.6.x. HTTP routers retain their explicit success and Problem Details contracts.
- Gateway uses `fastapi-rpckit[dishka]` 0.4.x. Declare operations directly with
  `channel.method`, `channel.event` and `channel.stream`.
- WebSocket admission remains in the presentation layer: authenticate before
  accepting any socket and register room presence for its connection lifetime.
  `serve_websocket` owns RPC transport cleanup and propagates task cancellation.
  The Dishka resolver receives the APP container and opens SESSION per connection
  and REQUEST per call.
- Generated SDKs include the current bounded queues, cancellation, connection
  errors, lifecycle signals and middleware runtime. Runtime packages are independent
  of the server distribution. Regenerate the contract and SDK together.
- SDK reconnect and automatic retries remain opt-in. Cara does not automatically
  repeat turn commands after an ambiguous disconnect or silently recover a socket
  whose application subscriptions have been lost.
- SSE and WebRTC are optional Canon transports. The existing voice binary stream
  remains the deployed media contract; this migration adds no unused transport.

## Client flow

1. Get or create the session via REST. Use creation for a fresh context and opening to resume the current session of a channel.
2. A history-oriented client loads the snapshot via `GET /v1/sessions/{id}`, then calls `subscription.subscribe` on the socket. Clients that intentionally follow whichever session is current for a channel use `subscription.subscribe_channel` instead.
3. The snapshot carries no event `sequence` yet, so events between steps 2 and 3 can be missed; a snapshot sequence would allow subscribe-first with dedupe.
