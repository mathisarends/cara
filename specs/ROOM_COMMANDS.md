# Room commands with Canon

## Decision and current scope

Canon's fastapi-rpckit 0.3 removed server-to-client RPC. Declare server operations
directly on `RpcChannel`; there is no `channel.server` or `channel.client` facade.
This replaces the earlier callback proposal in `PYRPCKIT_ISSUE_CALLBACKS.md`.

Cara currently implements room registration, connection-bound presence and state,
device and volume reports. It has no remote room-command implementation to migrate.
The design below is the contract for adding the first hardware command when its
use case is implemented; it does not introduce an unused command bus now.

## Transport and ownership

Keep the outbound authenticated room socket at `/v1/rooms/{room_id}/channel`.
The Gateway exposes a typed `room.command` event that only the addressed room's
connection receives. The room executes the command locally and calls the Gateway's
`room.complete_command` method with its outcome. Both declarations are ordinary
server-owned Canon operations, included in OpenRPC and generated into the SDK.

Use a discriminated union of concrete commands, for example `media.play` with its
media URI or `volume.set` with a validated level. Do not expose arbitrary method
names and JSON argument dictionaries. Results likewise use concrete success and
failure models with stable error codes.

An application-owned `RoomCommandService` orchestrates commands. Its inward-facing
delivery port uses domain values; `RpcConnection`, queues and generated SDK models
belong to presentation/infrastructure adapters. The room's application dispatcher
accepts local hardware ports and has no dependency on Gateway internals.

## Command lifecycle

1. Resolve the target room and active connection. Reject offline targets before
   allocating pending work.
2. Allocate a command UUID and record the pending command, expected room and
   connection generation before publishing its event. Bound both the queue and
   number of pending commands per room.
3. The room receives the event, validates the command variant and its expiry, then
   invokes the local use case. Return an explicit success or failure report using
   the same command UUID.
4. Resolve the pending result only from the authenticated socket that received
   the command. Take the room identity from the connection, never from caller
   supplied parameters. Reject reports from other rooms or older connections.
5. Remove pending state on completion, deadline, caller cancellation or disconnect.
   Duplicate and late reports cannot resolve another command. A deadline or lost
   connection means execution is uncertain, not that the hardware did nothing.

Delivery admission and hardware completion are separate facts. An awaitable use
case may wait for the report until its deadline. A longer operation should return
an operation ID and expose its persisted status as a REST resource.

## Recovery

`GatewayLink` remains the room's sole reconnect owner. After connection loss it
withdraws readiness, closes the old SDK, registers again and reports current state
on the new connection. Do not replay queued hardware commands across connections
or enable SDK retries for them. A reconnect does not prove a previous command
failed to execute.

Commands such as setting an absolute volume can later support deduplication with
the command UUID. Non-idempotent actions such as starting playback require an
explicit deduplication policy before retry is enabled. Durable delivery, replay
and exactly-once execution are outside this connection-bound design.

## Tests required with the first command

- Only the addressed connected room receives the typed command.
- Success and failure reports resolve the matching pending result.
- Other rooms and stale connections cannot complete it.
- Timeout, disconnect, cancellation, duplicates and late reports release pending
  state without replay or leaked tasks.
- Generated-client contract checks cover the command and outcome unions.

Upstream API: [Canon RPC migration](https://github.com/mathisarends/canon/blob/main/packages/fastapi-rpckit/CHANGELOG.md#030---2026-10-20).
