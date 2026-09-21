# Cara Room Client

One process represents one physical room. It owns the local Voice runtime,
registers the room's configured devices with the Gateway, keeps the room presence
alive over its WebSocket, and exposes local diagnostic endpoints.

```powershell
$env:CARA_GATEWAY_TOKEN = "..."
uv run --package room-client cara-room --config room/room.example.yml --voice-config voice.yml
```

The configured `room_id` must exist in `gateway.yml`. The process exposes
`/health` and `/ready` on its configured HTTP address.

The process is ready only while both its Gateway connection and Voice runtime
are available.
