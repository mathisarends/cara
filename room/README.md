# Cara Room Client

One process represents one physical room. It registers the room's configured
devices with the Gateway, keeps the room presence alive over its WebSocket, and
exposes local diagnostic endpoints.

```powershell
$env:CARA_GATEWAY_TOKEN = "..."
uv run --package room-client cara-room --config room/room.example.yml
```

The configured `room_id` must exist in `gateway.yml`. The client exposes
`/health`, `/ready`, `/room`, and `/devices` on its configured HTTP address.

The first slice deliberately owns only registration, presence, and reporting.
Audio, voice lifecycle, embodiment, and device commands move into this package
in the following slices.
