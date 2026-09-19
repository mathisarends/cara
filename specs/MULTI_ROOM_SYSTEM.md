@dataclass
class Room:
    id: RoomId
    name: str


@dataclass
class Device:
    id: DeviceId
    name: str
    room_id: RoomId | None
    kind: DeviceKind
    status: DeviceStatus


Device(
    id="living-room-pi",
    name="Living Room Node",
    room_id="living-room",
    kind=DeviceKind.COMPUTER,
)


class CapabilityKind(StrEnum):
    AUDIO_OUTPUT = "audio_output"
    AUDIO_INPUT = "audio_input"
    CAMERA = "camera"
    LIGHT = "light"
    PRESENCE = "presence"
    DISPLAY = "display"


## Multi-Room Concept

rooms:
  - id: living-room
    name: Wohnzimmer

devices:
  - id: living-room-node
    name: Wohnzimmer Node
    room: living-room
    kind: room_node
    capabilities:
      - audio_input
      - presence

  - id: living-room-sonos
    name: Sonos Wohnzimmer
    room: living-room
    kind: speaker
    capabilities:
      - audio_output

    integration:
      provider: sonos
      external_id: RINCON_123

Beim Start lädt dein Gateway das und baut da


Aber: online/offline, IP-Adresse, Verbindung, aktuelle Lautstärke usw. würde ich nicht in YAML pflegen.

Das kommt zur Laufzeit.

Dein Room Client könnte beim Gateway starten mit:

POST /devices/register

und etwa senden:

{
  "device_id": "living-room-node",
  "capabilities": [
    "audio_input",
    "presence"
  ]
}

Danach regelmäßig:

heartbeat
living-room-node
online=true
