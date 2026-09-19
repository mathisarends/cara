# Multi-Room System (Skizze)

## Ziel

Der Agent arbeitet mit **Räumen**, nicht mit Hardware.

> „Spiel im Wohnzimmer entspannten Jazz und dimme das Licht."
> „Sag im Schlafzimmer Bescheid, dass das Essen fertig ist."

Der Agent kennt weder Pi noch Sonos noch Hue. Hardware-Integration bleibt im Raum.

Die Architektur wird vollständig nach diesem Zielbild gebaut. Nur die Treiber sind auf die vorhandene Hardware beschränkt (siehe [Umfang](#umfang)); neue Geräte sind neue Treiber und Capability-Werte, keine Strukturänderung.

## Leitprinzipien

1. **Der Raum besitzt seine Geräte**: Mikrofon, Speaker, Licht, Media-Player. Alles, was Speaker oder Mikrofon braucht, läuft über den Raum.
2. **Voice ist der Gesprächsmodus des Raums**, nicht seine Identität. Die Voice-Bibliothek nutzt Mic und Speaker des Raums.
3. **Der Raum besitzt seine Embodiment-Semantik** (Raumzustand, Wake-Feedback, Earcons, Licht-Choreografie) und führt sie lokal aus, ohne Gateway-Roundtrip.
4. **Das Gateway besitzt die Home-Semantik**: Räume, Gruppen, Routing, Musik-Auflösung (Spotify).
5. **Der Raum ist proaktiv ansprechbar**: Das Gateway kann ohne Wake Word sprechen lassen, Musik und Licht steuern.
6. **Das Gateway adressiert Räume, keine Hardware.**
7. **Ein Binary, viele Räume**: Räume unterscheiden sich nur durch Config.

## Architektur

```
                  ┌────────────────────────────┐
                  │          Gateway           │
                  │  Room-/Device-Registry     │
                  │  Agent Runtime             │
                  │  Media Service (Spotify)   │
                  └─────────────┬──────────────┘
                                │ REST + Room-WebSocket + Voice-Session
          ┌─────────────────────┼─────────────────────┐
          ▼                     ▼                     ▼
   ┌─────────────┐       ┌─────────────┐       ┌─────────────┐
   │ Room Client │       │ Room Client │       │ Room Client │
   │ living-room │       │ kitchen     │       │ bedroom     │
   └──────┬──────┘       └─────────────┘       └─────────────┘
          ├─ Mic (PortAudio)
          ├─ Speaker (Sonos | lokal)
          └─ Licht (Hue)
```

| Ebene | Beispiel | Ort |
|---|---|---|
| Device-Treiber | „Lampe auf 30 %", „Sonos spielt URI" | Room Client |
| Raum-Semantik | Raumzustand, Earcons, Speaker-Vorrang | Room Client |
| Home-/Agent-Semantik | „Durchsage im ganzen Haus", „spiel Jazz" | Gateway |

## Begriffe

Zwei Ebenen, die nicht vermischt werden:

- **Device-Capability**: was Hardware kann. Der Room Client meldet sie pro Device (`audio_input`, `audio_output`, `media_playback`, `light`).
- **Raum-Funktion**: was der Agent mit einem Raum tun kann (`conversation`, `announce`, `music`, `light`). Das Gateway leitet sie aus den Capabilities der Devices ab.

| Raum-Funktion | benötigt |
|---|---|
| `conversation` | `audio_input` + `audio_output` |
| `announce` | `audio_output` |
| `music` | `media_playback` |
| `light` | `light` |

Der Agent sieht nur Räume und ihre Funktionen. Eine Funktion ist verfügbar, wenn der Raum online ist und die Capabilities gemeldet hat.

## Umfang

| Device | Treiber | Capabilities |
|---|---|---|
| Mikrofon | PortAudio | `audio_input` |
| Speaker | Sonos | `audio_output`, `media_playback` |
| Speaker | lokal (PortAudio) | `audio_output`, `media_playback` (über lokalen Spotify-Player, siehe [Musik](#musik)) |
| Licht | Hue | `light` |

Capability-Werte werden erst angelegt, wenn es einen Treiber dafür gibt; `display`, `camera`, `presence` kommen mit ihren Treibern.

## Domänenmodell (Gateway)

- **Room**: die Abstraktion, mit der der Agent arbeitet.
- **RoomGroup**: benannte Menge von Räumen (z. B. `downstairs`, `everywhere`).
- **Device**: Hardware, einem Raum zugeordnet, mit Capabilities.

Die **Topologie** (Räume, Gruppen, Anzeigenamen und Aliase für den Agenten) steht in `gateway.yml`. Devices und Capabilities meldet der Room Client bei der Registrierung; das Gateway lehnt Räume ab, die nicht in der Topologie stehen. **Laufzeitzustand** (online, Device-Status, Raumzustand, Now Playing, Lautstärke) lebt nur im Speicher des Gateways und verfällt mit der Verbindung.

`VoiceSession` referenziert den Raum per `room_id` und wird gegen die Registry validiert.

## Room Client

Ein Prozess pro Raum (`clients/room`, Package `room`), der die Geräte des Raums besitzt, sich beim Gateway anmeldet und dessen Kommandos ausführt. Alle Räume nutzen dasselbe Binary bzw. Docker-Image; `room_id`, Gateway und Geräte kommen aus der Config. Keine raumspezifischen Klassen.

### Schichten

Der Room Client folgt denselben Schichten wie die Gateway-Features. Abhängigkeiten zeigen nur nach innen: `presentation` und `infrastructure` → `application` → `domain`. Treiber, Voice-Bibliothek und Gateway-Clients kennt nur `infrastructure`.

```
room/
  __main__.py              # python -m room --config living-room.yaml
  bootstrap.py             # Composition Root: Config → Treiber → Services → Room.run()

  domain/                  # reine Raum-Semantik, kein I/O
    room.py                # Room (Aggregat): room_id, Devices, RoomState, Media-Status
    device.py              # Device, DeviceKind, Capability, DeviceStatus
    state.py               # RoomState und Übergänge aus Gesprächs- und Wiedergabe-Fakten
    speaker.py             # SpeakerClaim (voice | earcon | music), Vorrangregel, Arbitrierungs-Entscheid
    commands.py            # RoomCommand: MediaPlay, MediaPause, …, LightSet
    embodiment.py          # Zuordnung RoomState → Licht-Szene / Earcon
    errors.py

  application/             # Anwendungsfälle, orchestriert über Ports
    ports.py               # ABCs: Microphone, Speaker, MediaPlayer, Light, EarconPlayer,
                           #       ConversationEngine, GatewayRegistry, RoomReporter
    conversation.py        # ConversationService: Gespräch starten, nach Ende neu aufbauen
    commands.py            # CommandService: RoomCommand ausführen, Capability prüfen
    arbitration.py         # SpeakerArbiter: setzt den Domain-Entscheid an Speaker/MediaPlayer um
    embodiment.py          # EmbodimentService: reagiert auf RoomState mit Licht und Earcons
    registration.py        # RegistrationService: anmelden, nach Reconnect erneut
    reporting.py           # meldet RoomState, Device- und Media-Status ans Gateway
    readiness.py           # Readiness-Bedingungen für /ready

  infrastructure/          # Adapter nach außen (driven)
    config.py              # RoomConfig (pydantic-settings, YAML)
    devices/
      portaudio.py         # Microphone + lokaler Speaker
      sonos.py             # Speaker + MediaPlayer über Sonos
      librespot.py         # MediaPlayer lokal (Spotify Connect → Mixer)
      hue.py               # Light
    audio/
      echo_cancellation.py # AEC-Stack um Mic und lokalen Speaker
      mixer.py             # lokaler Mixer für Stimme, Earcons, Musik
      earcons.py           # EarconPlayer
    voice.py               # ConversationEngine über voice.VoiceSessionFactory;
                           # Voice-Lifecycle → Gesprächs-Fakten für RoomState
    gateway/
      registry.py          # GatewayRegistry über GatewayRestClient
      link.py              # Room-WebSocket, Reconnect mit Backoff
      reporter.py          # RoomReporter über die Room-WebSocket

  presentation/            # Eingänge (driving)
    gateway_commands.py    # Event room.command → CommandService, Quittung completed/failed
    http.py                # /health /ready /room /devices
```

Zuordnungsregeln:

- **Domain** entscheidet, ohne auszuführen: welcher Zustand aus welchem Fakt folgt, wer den Speaker bekommt, welche Reaktion zu welchem Zustand gehört, welches Kommando welche Capability braucht.
- **Application** führt Entscheidungen über Ports aus und kennt weder Sonos noch Hue noch die Voice-Bibliothek. `ConversationEngine` ist der Port für die Voice-Bibliothek: gebaut wird die Session in `infrastructure/voice.py`, der Lebenszyklus (bauen, ausführen, neu aufbauen) liegt in `ConversationService`.
- **Infrastructure** übersetzt in beide Richtungen: Treiber-Aufrufe nach außen, Voice-Lifecycle-Events nach innen in Domain-Fakten.
- **Presentation** nimmt Kommandos vom Gateway und Diagnose-Anfragen an und ruft nur Application-Services auf. Ausgehende Gateway-Kommunikation (Registrierung, Zustandsmeldungen) ist ein Port und liegt in `infrastructure`.

`Room.run()` in `bootstrap.py` startet Gateway-Link, `ConversationService` und HTTP-Server in einer `TaskGroup`. Ohne Gateway laufen lokale Reaktionen weiter; Gespräche, Durchsagen und Musik brauchen das Gateway.

### Gateway-Feature `room`

Im Gateway ein Feature `gateway/features/room/` mit denselben Schichten:

- `domain/`: `Room`, `RoomGroup`, `Device`, `Capability`, `RoomFunction` und die Ableitung Funktion ← Capabilities.
- `application/`: `RoomRegistryService` (Registrierung, Online-Status, Auflösen von Gruppen), `RoomCommandService` (Kommando schicken, auf Quittung warten), Ports für Topologie und Verbindungen.
- `infrastructure/`: Topologie aus `gateway.yml`, In-Memory-Laufzeitzustand, Provider.
- `presentation/`: REST-Router (`/v1/rooms`, Registrierung), RPC-Kanal `room` (Verbindung, Quittungen, Zustandsmeldungen, Event `room.command`).

Der Media Service ist ein eigenes Feature `media` und nutzt `RoomCommandService`; Voice nutzt die Registry zur Validierung von `room_id`.

### Raumzustand

`RoomState` (`IDLE`, `LISTENING`, `THINKING`, `SPEAKING`) gehört dem Raum. Er wird lokal abgeleitet: aus dem Voice-Lifecycle (der Raum hängt sich als `VoiceLifecycleObserver` an) und aus der eigenen Wiedergabe. Licht und Earcons reagieren auf `RoomState`, nicht auf Voice-Callbacks. Damit ersetzen sie die heutigen `VoiceIntegration`s; `VoiceIntegration` entfällt.

Das Gateway setzt den Raumzustand nicht, es sieht ihn nur (gemeldet über die Room-WebSocket).

### Registrierung und Verbindung

Regel aus `docs/gateway-transport.md`: REST für CRUD und Topologie, WebSocket nur für Zustand, der an eine lebende Verbindung gebunden ist.

1. **Registrieren** per REST (`PUT /v1/rooms/{room_id}/registration`): Devices mit Capabilities, Client-Version. Idempotent.
2. **Verbinden** per Room-WebSocket, Wiederverbinden mit Backoff, danach erneut registrieren.
3. **Online-Status = Verbindung.** Solange die Socket lebt, ist der Raum online. Keepalive läuft über die WebSocket.

### Schnittstelle zwischen Gateway und Raum

pyrpckit kennt nur Requests vom Client zum Server; der Server schickt Events. Deshalb:

- **Kommandos** schickt das Gateway als Event `room.command` mit `command_id` an den Raum.
- Der Raum **quittiert** per Request `room.command.completed` bzw. `room.command.failed`. Das Gateway wartet mit Timeout auf die Quittung und meldet dem Agenten das Ergebnis.
- Der Raum **meldet Zustand** per Request: Raumzustand, Device-Status, Media-Status (Now Playing, Lautstärke).

Kommandos:

| Kommando | Capability |
|---|---|
| `media.play(uri)`, `media.pause`, `media.resume`, `media.stop`, `media.set_volume` | `media_playback` |
| `light.set(on, brightness, color)` | `light` |

**Durchsagen** laufen nicht über die Room-WebSocket, sondern als proaktiver Voice-Turn über die Voice-Session des Raums (`start_proactive_in_room`), weil dort Audio-Streaming, Echo-Cancellation und die anschließende Antwort des Nutzers schon gelöst sind.

### HTTP am Room Client

Nur lokal für Diagnose.

```
GET /health   GET /ready   GET /room   GET /devices
```

- `/health` (Liveness): Prozess läuft, Event-Loop antwortet. Unabhängig von Gateway und Hardware.
- `/ready` (Readiness): Config geladen, Treiber initialisiert, beim Gateway registriert. Sonst `503` mit den fehlenden Bedingungen.

### Config

Pro Raum eine Datei:

```yaml
room_id: living-room
gateway:
  url: http://gateway:8000   # Token aus CARA_GATEWAY_TOKEN
devices:
  microphone:
    driver: portaudio
  speaker:
    driver: sonos            # oder: local
    ip_address: 192.168.1.20
  light:
    driver: hue
    room_name: Wohnzimmer
conversation:                # bisheriges VoiceSessionConfig ohne Geräte, Raum, Gateway
  activation: ...
  barge_in: ...
  session: ...
embodiment:
  earcons: true
  light: true
arbitration:
  music_during_voice: duck   # oder: pause
```

## Speaker und Audio

Der Speaker wird von Assistentenstimme, Earcons und Musik benutzt. Der Raum entscheidet den Vorrang: **Stimme vor Earcon vor Musik**; Musik wird geduckt oder pausiert. Das ersetzt die heutige `SonosAudioFocusIntegration`.

Der Raum besitzt den **AEC-Stack**: Mic und Speaker werden im Raum mit Echo-Cancellation gewickelt, und Voice bekommt die gewickelten Geräte. Alles, was über den lokalen Speaker läuft (Stimme, Earcons, lokale Musik), läuft durch den Output mit Echo-Referenz.

| Speaker | Stimme / Earcons | Musik | Echo-Referenz für Musik |
|---|---|---|---|
| lokal | Mixer im Raum | Mixer im Raum | ja |
| Sonos | Clips über Sonos | Sonos spielt selbst | nein; Musik wird während des Zuhörens geduckt oder pausiert |

## Musik

Musik ist Spotify-Wiedergabe im Raum, keine Sound-Bibliothek.

- **Gateway** (Media Service): löst Anfragen über die Spotify-API auf (Spotify-Auth nur hier), bestimmt Ziel-Räume mit `music` und schickt `media.play`.
- **Room Client**: spielt über den Speaker-Treiber, arbitriert gegen Stimme und Earcons und meldet Now Playing zurück.
  - **Sonos**: Sonos spielt die Spotify-URI selbst. Voraussetzung: Spotify ist im Sonos-Haushalt verknüpft.
  - **lokal**: ein lokaler Spotify-Connect-Player (librespot) gibt PCM an den Mixer des Raums, damit die Musik durch Arbitrierung und Echo-Referenz läuft. Der Raum meldet die Connect-Device-ID bei der Registrierung; das Gateway startet die Wiedergabe per Spotify-API auf diesem Device.
- Now Playing ist Laufzeitzustand des Raums und für den Agenten abfragbar.

`voice.audio.AudioOutput` (PCM-Senke für die Assistentenstimme) bleibt von der Musikwiedergabe getrennt.

## Licht

Hue ist ein Device mit `light`. Der Raum nutzt es auf zwei Arten:

- **Embodiment**: lokale Choreografie auf `RoomState` (heutige Hue-Integration).
- **Kommando**: `light.set` vom Gateway („dimme das Licht"). Ein Kommando setzt die neue Grundhelligkeit; Embodiment-Effekte kehren danach zu ihr zurück.

## Proaktivität

Ohne Wake Word kann das Gateway einen Raum sprechen lassen (Erinnerung, Alarm, Durchsage), Musik oder Licht steuern. Bei Gruppen löst das Gateway die Räume auf und verteilt; jeder Raum führt mit seiner lokalen Semantik aus. Offline-Räume und Räume ohne die nötige Funktion werden übersprungen und im Ergebnis genannt.

## Voice als Bibliothek

`clients/voice` wird reine Bibliothek, die Room-Schicht kennt sie nicht (`room ──► voice`, nie umgekehrt). `room` ist das einzige Binary; die Voice-Beispiele ziehen in den Room Client.

- `VoiceSessionConfig` verliert `gateway`, `room`, `sonos`, `audio.output` und `integrations`. `VoiceSessionFactory` bekommt `room_id`, Backend-Connector, die (AEC-gewickelten) Geräte und `observers` injiziert.
- `VoiceSession` bleibt one-shot; der Room Client baut sie nach jedem Ende neu.
- Hue, Earcons und Sonos-Audio-Focus ziehen ins Room-Paket und reagieren dort auf `RoomState`; `VoiceIntegration` entfällt.

## Migrationspfad

1. Gateway: `rooms`-Feature mit Topologie aus `gateway.yml`, Registrierung per REST, Registry lesbar; `VoiceSession.room` → `room_id` mit Validierung.
2. Room Client: Config, Treiber für Mikrofon und Speaker, Registrierung, Room-WebSocket mit Reconnect, `/health`, `/ready`.
3. Voice als Bibliothek: Config aufteilen, AEC in den Raum, Gesprächsmodus im Room Client.
4. `RoomState` und Embodiment (Earcons, Hue) im Room-Paket; Speaker-Arbitrierung.
5. Kommandos über die Room-WebSocket mit Quittung; `light.set`.
6. Musik: Media Service im Gateway, Sonos-Wiedergabe, danach lokaler Player.
7. Agent-Tools auf Raum-Funktionen, `RoomGroup`-Fan-out.

## Offene Fragen

- Zwei Verbindungen pro Raum (Room-WebSocket + Voice-Session) oder später zusammenlegen?
- Strikt ein Raum pro Prozess oder mehrere Räume in einem Prozess?
- Lokaler Spotify-Player: librespot als Subprozess mit Pipe-Backend oder eingebettet?
- Sonos-Gruppierung für synchrone Musik über mehrere Räume.
- Sonos-Musik hat keine Echo-Referenz: reicht Ducken während des Zuhörens, oder muss Barge-in bei Sonos-Musik anders konfiguriert werden?
