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

- Full-duplex PCM audio uses a dedicated binary socket with a compact versioned frame header.
- The authenticated connection is the sole input/output owner of that voice session.
- Audio never passes through JSON-RPC; input completion is an ordered media frame.

## REST

- Sessions: `POST /v1/sessions`, `POST /v1/sessions/open`, `GET /v1/sessions/{id}`
- Automations: `/v1/owners/{owner_id}/automations` (CRUD)
- Alarms: `/v1/owners/{owner_id}/alarms` (CRUD, `enabled`, `skip-next`, `snooze`, `dismiss`)
- Voice sessions: `POST /v1/voice-sessions`, list/get/close, and persisted turn snapshots
- Future resource features: REST only, no RPC layer
- Every resource router requires `Authorization: Bearer <CARA_GATEWAY_TOKEN>` (`require_token`, OpenAPI scheme `GatewayToken`); only health is open

## Contracts and clients

| Contract | Schema | Generated client |
| --- | --- | --- |
| REST | `gateway/schema/openapi.json` | `generated/gateway_rest_client` (`GatewayRestClient`, httpxgen) |
| RPC | `gateway/schema/gateway.openrpc.json` | `generated/gateway_rpc_client` (`GatewayRpcClient`, pyrpckit) |

- Regenerate both: `scripts/codegen/generate_gateway_clients.sh`
- CI (`gateway-schema-drift.yml`) reruns it and fails on any diff or untracked file
- Clients configure one base URL (`http://host:port`); `connect_gateway` derives `ws(s)://host:port/v1/gateway`
- REST discriminated-union members declare their tag (`kind`/`type`) without a default: httpxgen rejects a discriminator that is both required and defaulted

## Client flow

1. Get or create the session via REST. A client that wants ephemeral context may pass `inactivity_timeout_seconds`; omitting it means that the session never expires automatically.
2. A history-oriented client loads the snapshot via `GET /v1/sessions/{id}`, then calls `subscription.subscribe` on the socket. A persistent channel client such as Voice calls `subscription.subscribe_channel` instead.
3. The snapshot carries no event `sequence` yet, so events between steps 2 and 3 can be missed; a snapshot sequence would allow subscribe-first with dedupe.
