# Gateway Transport: REST vs. WebSocket RPC

Rule: WebSocket RPC only for state bound to a live connection or an active turn. Everything else (CRUD, session lookup, initial load) is REST.

## WebSocket (`/v1/gateway`, JSON-RPC)

- `subscription.subscribe` / `subscription.unsubscribe`: connection-bound (`client_id`)
- `turn.start`: result arrives as events on the socket anyway
- `turn.steer` / `turn.cancel`: control a running turn
- `turn.prepare` / `turn.finish`: latency-sensitive agent lifecycle hints during a conversation
- Notification `session.event`

## REST

- Sessions: `POST /v1/sessions`, `POST /v1/sessions/open`, `GET /v1/sessions/{id}`
- Automations: `/v1/owners/{owner_id}/automations` (CRUD)
- Alarms and future features: REST only, no RPC layer

## Removed from RPC

- `automation.*`: duplicated REST
- `session.create` / `session.open` / `session.get`: duplicated REST

## Client flow

1. Get or create the session via REST.
2. Connect the socket and call `subscription.subscribe`.
3. Load the snapshot via `GET /v1/sessions/{id}` and drop any event whose `sequence` is at or below the snapshot state. Subscribe before loading the snapshot so no event is lost in between.
