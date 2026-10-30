# Voice als Capability des Room-Clients

## Ziel

Der Room-Client wird der lokale Prozess für einen physischen Raum. Er besitzt die
Geräte dieses Raums und stellt daraus unter anderem eine Voice-Capability bereit.
Ein separater Voice-Client mit eigener Raum-, Audio-, Sonos- und Hue-Konfiguration
existiert danach nicht mehr als eigenständige Anwendung.

Wenn das Wake Word in einem Raum erkannt wird, öffnet beziehungsweise verwendet die
lokale Voice-Capability eine Gateway-Voice-Session mit der stabilen `room_id` dieses
Raums. Jeder daraus gestartete Agent-Turn erhält einen typisierten Room-Kontext. Damit
können die Agent-Runtime und deren raumbezogene Tools erkennen, in welchem Raum die
Anfrage entstanden ist.

Die normale Conversation-Session bleibt bewusst raumagnostisch. Eine Conversation
kann auch aus Text- oder zukünftigen anderen Clients stammen und benötigt per se keine
`room_id`. Die Zuordnung gilt ausschließlich für eine Voice-Session und wird nur für
Voice-ausgelöste Agent-Turns in den Ausführungskontext projiziert.

## Begriffe

- **Room**: ein physischer Raum mit stabiler UUID und lokal verfügbaren Geräten.
- **Gerät**: konkrete Hardware wie Mikrofon, lokaler Lautsprecher, Sonos-Speaker
  oder Hue-Licht.
- **Geräte-Capability**: elementare Fähigkeit eines Geräts, zum Beispiel Audio
  aufnehmen, Audio wiedergeben, Medien steuern oder Licht darstellen.
- **Room-Capability**: aus einem oder mehreren Geräten zusammengesetztes Verhalten
  des Raums. Voice und Wake Word sind Room-Capabilities, keine eigenständigen Räume
  oder Remote-Clients.
- **Voice-Session**: Gateway-seitige, langlebige Verbindung eines konkreten Raums
  für Voice-Turns und proaktive Sprachausgabe.
- **Conversation-Session**: kanalbezogener Gesprächsverlauf. Sie kennt den Raum
  nicht und speichert keine Room-Metadaten.
- **Embodiment**: raumeigene, austauschbare Darstellung des Assistant-Zustands,
  beispielsweise durch Licht, Earcons, ein Display oder eine andere physische Form.

## Scope

Diese Spec umfasst:

1. die Integration der bestehenden Voice-Runtime in den Room-Client;
2. Wake-Word-Erkennung als optionale Capability eines Raums;
3. eine typisierte `room_id` auf der Voice-Session;
4. die Weitergabe des Room-Kontexts an Voice-ausgelöste Agent-Turns;
5. raumeigene Audio-Ein- und -Ausgabe;
6. raumeigenes Audio-Fokus-Verhalten wie Sonos Ducking oder Pause;
7. ein offenes Embodiment-Interface für Licht, Earcons und zukünftige Darstellungen;
8. die Migration von `voice.yml` in die Konfiguration des Room-Clients.

Nicht Teil dieser Spec sind:

- Shell-Tools, Sandbox-Verhalten oder die Auswahl und Ausführung von Skills;
- eine allgemeine Herkunftsmodellierung für Textnachrichten oder andere Clients;
- die Zuordnung einer `room_id` zu jeder Conversation-Session;
- raumübergreifendes Beamforming oder die Auswahl zwischen mehreren gleichzeitig
  auslösenden Räumen;
- eine vollständige Remote-Steuerung aller Room-Geräte;
- die Festlegung, dass Embodiment immer Licht sein muss;
- die Verlagerung von STT oder TTS aus dem Gateway auf den Room-Client.

## Bestehender Zustand

Heute laufen Room- und Voice-Client nebeneinander:

- Der Room-Client registriert eine UUID und eine Liste von Geräten beim Gateway,
  hält die Room-Verbindung offen und meldet Zustand, Gerätestatus und Lautstärke.
- Der Voice-Client besitzt Mikrofon, Ausgabe, Wake Word, Echo Cancellation, Barge-in,
  Sonos-Audio-Fokus, Hue-Licht und Earcons.
- Der Voice-Client identifiziert seinen Raum mit einem freien String `room`.
- Das Gateway speichert diesen String als `voice_sessions.device_id` und verwendet
  ihn unter anderem für Eindeutigkeit und proaktive Auslieferung.
- Die Conversation-Session enthält nur den Channel. Beim Aufbau von
  `AgentSessionRef` geht der Room-Kontext verloren.
- Raumeigene Geräte werden doppelt beschrieben: einmal im Room-Client und erneut in
  `voice.yml` beziehungsweise in der Voice-Factory.

Dadurch ist die fachliche Ownership umgedreht: Nicht der Raum spricht, hört, dimmt
oder pausiert seine Medien, sondern ein separater Voice-Prozess verwaltet zufällig
dieselben physischen Ressourcen.

## Zielarchitektur

```text
Room process
├─ Room (room_id, devices, state)
├─ device adapters
│  ├─ audio input / microphone
│  ├─ audio output / local or Sonos speaker
│  ├─ media focus / Sonos pause or duck
│  └─ embodiment / Hue, earcons, display, ...
└─ Voice capability
   ├─ wake-word activation
   ├─ echo cancellation and barge-in
   ├─ voice lifecycle orchestration
   └─ Gateway voice backend
          |
          | OpenVoiceSession(room_id: UUID, ...)
          v
Gateway
├─ VoiceSession(room_id, conversation_session_id, ...)
├─ STT / TTS / voice media
└─ VoiceTurnService
       |
       | AgentTurnContext(room=RoomContext(room_id))
       v
   Agent runtime and turn-scoped tools
```

Die bestehende `voice`-Package kann dabei als interne, hardwareunabhängige Engine
erhalten bleiben. Entscheidend ist nicht das Verzeichnis, sondern die Ownership:
Der Room-Client ist Composition Root und Lifecycle-Owner. Er injiziert die Geräte,
Room-Integrationen und `room_id` in die Voice-Capability. Die Voice-Engine liest keine
zweite Raum- oder Hardwarekonfiguration mehr.

## 1. Room-ID gehört auf die Voice-Session

Der freie String `room` wird durch `room_id: UUID` ersetzt. Das gilt durchgängig für:

- `BackendConnectionOptions` im lokalen Voice-Code;
- `OpenVoiceSessionRequest` und `VoiceSessionResponse`;
- das Gateway-Domainmodell `VoiceSession`;
- Repository-Filter und Eindeutigkeitsregeln;
- proaktive Voice-Auslieferung;
- Alarm- und Automation-Delivery, soweit diese einen Zielraum referenzieren.

Beispiel für den Transportvertrag:

```python
class OpenVoiceSessionRequest(ApiModel):
    session_id: UUID
    room_id: UUID
    input_formats: tuple[AudioFormat, ...]
    output_formats: tuple[AudioFormat, ...]
```

`room_id` ist keine frei erweiterbare Metadata-Map. Im Domain- und
Application-Code wird sie als `UUID` geführt. Auch persistiert wird eine typisierte
Spalte `room_id`, keine JSON-Spalte.

Beim Öffnen validiert das Gateway die ID gegen die Room-Registry. Eine Voice-Session
darf nur geöffnet werden, wenn:

- der Raum in der Gateway-Topologie existiert;
- der Room-Client registriert und verbunden ist;
- der Raum die für Voice notwendigen Capabilities gemeldet hat;
- für diesen Raum noch keine offene Voice-Session existiert.

Die Gateway-Fremdschlüsselbeziehung zur aktuell speicherinternen Room-Registry wird
nicht erzwungen. Die fachliche Validierung erfolgt über `RoomRegistryService`; die
Voice-Session speichert weiterhin selbstständig die UUID, damit ihr Verlauf erhalten
bleibt, wenn ein Room-Client offline geht.

## 2. Conversation-Sessions bleiben raumagnostisch

`Session`, `CreateSessionRequest`, `OpenSessionRequest` und die zugehörige
Persistenz erhalten keine `room_id` und keine generische `metadata`.

Der Voice-Client darf weiterhin eine Conversation-Session erzeugen und deren ID beim
Öffnen der Voice-Session mitsenden. Die Room-Zuordnung entsteht erst durch:

```text
VoiceSession(conversation_session_id, room_id)
```

Wenn eine Voice-Konversation nach Inaktivität auf eine neue Conversation-Session
wechselt, bleibt dieselbe Voice-Session samt `room_id` bestehen. Die neue
Conversation-Session bleibt ebenfalls raumagnostisch.

Diese Abgrenzung verhindert, dass Text-Clients oder zukünftige Eingabegeräte in ein
verfrühtes gemeinsames Provenance-Modell gezwungen werden.

## 3. Typisierter, turngebundener Agent-Kontext

Der Room-Kontext wird nicht nachträglich aus einer Dictionary-Metadata gelesen und
nicht in der Conversation-Session gespeichert. `VoiceTurnService` kennt beim Start
des Conversation-Turns sowohl die Voice-Session als auch deren `room_id` und erstellt
daraus einen typisierten Ausführungskontext.

Ein möglicher Application-Vertrag ist:

```python
@dataclass(frozen=True, slots=True)
class RoomContext:
    room_id: UUID


@dataclass(frozen=True, slots=True)
class AgentTurnContext:
    room: RoomContext | None = None
```

`TurnWorker.start` und `TurnWorker.start_scheduled` akzeptieren optional einen
`AgentTurnContext`. `VoiceTurnService` übergibt immer
`AgentTurnContext(room=RoomContext(voice_session.room_id))`. Normale Conversation-
Aufrufe verwenden den Default ohne Room-Kontext.

Der Kontext wird bis in `AgentRunRequest` weitergereicht. Die konkrete Agent-Runtime
stellt ihn turngebunden den Komponenten zur Verfügung, die ihn benötigen:

- Kontextaufbereitung beziehungsweise System-Prompt-Erweiterung;
- Gateway-eigene Tool-Dependencies;
- zukünftige raumbezogene Tools oder Skills.

Dabei gelten folgende Regeln:

- Der Context ist ein Value Object, kein `dict[str, Any]`.
- Kein Consumer sucht selbst anhand der Conversation-Session nach einer offenen
  Voice-Session.
- Der Agent-Cache darf den Kontext nicht vom ersten Turn dauerhaft einfrieren.
  Raumabhängige Werte werden pro Turn bereitgestellt oder beim erneuten Verwenden
  eines Agents explizit aktualisiert.
- Ein normal gestarteter Text-Turn erhält `room=None`, auch wenn zufällig eine
  Voice-Session dieselbe Conversation-Session referenziert.
- Voice-Follow-up-Turns und proaktive Voice-Turns erhalten denselben Room-Kontext wie
  der initiale Wake-Word-Turn.

Die vorhandene Reminder-Logik soll dadurch einfacher werden: Sie muss den Zielraum
nicht mehr indirekt aus aktiven Voice-Sessions und Media-Verbindungen erraten, sondern
kann bei einem Voice-Turn direkt `context.room.room_id` als typisiertes Delivery-Ziel
verwenden. Für Turns ohne Room-Kontext bleibt das bisherige nicht-räumliche Verhalten
bestehen.

## 4. Voice ist eine Room-Capability

Der Room-Client startet die Voice-Runtime nur, wenn seine Konfiguration eine
Voice-Capability definiert und die benötigten Geräte auflösbar sind. Die
Voice-Capability besteht fachlich aus:

- einer oder mehreren Activation Sources, insbesondere Wake Word;
- einem Audio-Input;
- einem Audio-Output;
- optionaler Echo Cancellation;
- einer Barge-in-Strategie;
- dem Gateway-Voice-Backend;
- optionalem Audio-Fokus;
- optionalen Embodiments.

Die lokale `Room`-Domain bleibt eine Beschreibung von Identität, Geräten und
beobachtbarem Zustand. Laufende Tasks, Netzwerkverbindungen und Hardwarehandles
gehören nicht in das Aggregate. Eine Application-Komponente wie
`RoomVoiceCapability` oder `VoiceService` besitzt den Runtime-Lifecycle und wird vom
Room-Lifespan gestartet und beendet.

Wake Word ist eine Capability des Raums, nicht des Mikrofons. Das Mikrofon liefert
lediglich Audio-Input. Erst die Kombination aus Audio-Input, Wake-Word-Detector und
Voice-Orchestrierung ergibt beispielsweise `RoomCapability.WAKE_WORD` und
`RoomCapability.CONVERSATION`.

Geräte-Capabilities und zusammengesetzte Room-Capabilities dürfen nicht im selben
Enum vermischt werden. Die heute gleichnamigen `Capability`-Typen auf Client- und
Gateway-Seite sollen bei der Umsetzung eindeutig benannt und vollständig migriert
werden, beispielsweise:

```python
class DeviceCapability(StrEnum):
    AUDIO_INPUT = "audio_input"
    AUDIO_OUTPUT = "audio_output"
    MEDIA_PLAYBACK = "media_playback"
    LIGHT_OUTPUT = "light_output"


class RoomCapability(StrEnum):
    WAKE_WORD = "wake_word"
    CONVERSATION = "conversation"
    ANNOUNCEMENT = "announcement"
    MEDIA = "media"
    EMBODIMENT = "embodiment"
```

Welche Room-Capabilities tatsächlich verfügbar sind, wird aus Konfiguration,
erfolgreich geöffneten Adaptern und Gerätestatus abgeleitet und bei der
Room-Registrierung beziehungsweise bei Statusänderungen ans Gateway gemeldet.

## 5. Audio, Speaker und Audio-Fokus gehören dem Raum

Mikrofon und Speaker werden genau einmal in `room.yml` beschrieben und vom
Room-Client geöffnet. Die Voice-Engine erhält bereits geöffnete Ports beziehungsweise
Factories und kennt keine IP-Adressen, Hue-Raumnamen oder PortAudio-Geräte-IDs.

Ein Speaker kann mehrere elementare Fähigkeiten anbieten:

- Voice-PCM wiedergeben;
- Medien wiedergeben;
- Lautstärke lesen und setzen;
- Audio-Fokus durch Ducking oder Pause gewähren.

Nicht jeder Audio-Output muss alle Fähigkeiten implementieren. Die
Room-Komposition validiert deshalb explizit, welche Ports für die konfigurierte
Voice- und Focus-Strategie erforderlich sind. Es gibt keine defensiven
`getattr`-Abfragen auf optionale Methoden.

STT und TTS bleiben Gateway-Capabilities. Aus Sicht des Raums laufen Spracheingabe
und Sprachausgabe zwar über seine Voice-Capability, aber der lokale Prozess stellt nur
Audio-Aufnahme, Audio-Wiedergabe und den Voice-Transport bereit. Provider-Auswahl und
Credentials bleiben im Gateway.

## 6. Embodiment statt Voice-spezifischer Integrationen

Hue-Licht, Earcons und zukünftige physische Reaktionen werden nicht als beliebige
`VoiceIntegration` mit Zugriff auf interne Voice-Details modelliert. Der Raum bietet
ein kleines, fachliches Embodiment-Interface an, auf das Voice-Lifecycle-Ereignisse
abgebildet werden.

Die Schnittstelle soll Zustände und relevante Ereignisse ausdrücken, aber keine
Technologie vorgeben. Ein möglicher Vertrag ist:

```python
class RoomEmbodiment(ABC):
    @abstractmethod
    async def set_state(self, state: RoomState) -> None: ...

    async def wake_word_detected(self) -> None: ...

    async def conversation_ended(self) -> None: ...

    async def failure(self) -> None: ...
```

Die genaue Zahl der Event-Methoden soll sich am tatsächlich benötigten Verhalten
orientieren. Das Interface darf nicht einfach alle heutigen
`VoiceIntegration`-Callbacks kopieren. Stabile Zustände wie `IDLE`, `LISTENING`,
`THINKING` und `SPEAKING` werden bevorzugt; punktuelle Signale wie Wake-Earcon oder
Fehler können ergänzt werden.

Adapter können sein:

- Hue-basierte Licht-Ambience;
- Earcons über den raumeigenen Audio-Output;
- ein zusammengesetztes Embodiment aus mehreren Adaptern;
- zukünftig Display, Animation oder andere Hardware.

Audio-Fokus ist davon getrennt. Ducking und Pause sind keine visuelle Darstellung
des Assistant-Zustands, sondern eine raumeigene Medienkoordination. Eine
`RoomAudioFocus`-Abstraktion reagiert auf Beginn und Ende einer Voice-Konversation
und stellt den vorherigen Zustand idempotent wieder her.

Fehlersemantik:

- Kann eine für Voice zwingende Ressource nicht vorbereitet werden, wird die
  Voice-Capability nicht ready und der Room-Client meldet den Grund.
- Ein späterer Fehler eines optionalen Embodiment-Adapters beendet keinen laufenden
  Voice-Turn; der Adapter wird als fehlerhaft gemeldet und der Fehler geloggt.
- Audio-Fokus muss auch bei Abbruch, Backend-Disconnect und Shutdown freigegeben
  werden.

## 7. Konfiguration

`voice.yml` entfällt als Anwendungskonfiguration. Die relevanten Werte wandern unter
eine optionale `voice`-Sektion in `room.yml`; Hardware bleibt unter `devices`.

Beispiel:

```yaml
room_id: 8edc5cf8-0caa-4d5a-9b5b-10da42dfdde2
gateway:
  url: http://127.0.0.1:8000
  token: change-me-gateway-token-32-characters
  heartbeat_seconds: 15

devices:
  - device_id: microphone
    driver: portaudio

  - device_id: speaker
    driver: sonos
    ip_address: 192.168.1.20

  - device_id: ambience
    driver: hue
    room_name: Mein Zimmer

voice:
  input_device: microphone
  output_device: speaker
  activation:
    wake_word:
      word: hey_mycroft
      sensitivity: 0.5
      cooldown_seconds: 1.5
      strip_from_command: true
  barge_in:
    type: wake_word
  echo_cancellation:
    enabled: true
  audio_focus:
    device: speaker
    strategy: duck
  embodiments:
    - device: ambience
      type: light
    - device: speaker
      type: earcons
```

Referenzen auf `device_id` werden beim Start validiert. Eine Voice-Konfiguration ist
ungültig, wenn beispielsweise:

- Input oder Output fehlt;
- ein referenziertes Gerät die benötigte Geräte-Capability nicht anbietet;
- Wake-Word-Barge-in ohne Wake-Word-Activation konfiguriert ist;
- Ducking für ein Gerät ohne Audio-Fokus-Port verlangt wird;
- dieselbe exklusive Hardware widersprüchlich konfiguriert ist.

Secrets werden weiterhin über Umgebungsvariablen überschrieben. Es gibt nach der
Migration keine zweite `room`- oder `sonos`-Konfiguration im Voice-Package.

## 8. Lifecycle und Zustandsfluss

### Startup

1. Der Room-Client lädt und validiert `room.yml`.
2. Er erstellt das Room-Aggregate und öffnet die konfigurierten Geräteadapter.
3. Er leitet die tatsächlich verfügbaren Room-Capabilities ab.
4. Er registriert Raum, Geräte und Capabilities beim Gateway und öffnet die
   Room-Verbindung.
5. Falls Voice konfiguriert und bereit ist, öffnet er eine Gateway-Voice-Session mit
   `room_id=room.room_id` und startet die Voice-Runtime.
6. Erst danach ist die Wake-Word-Capability ready.

Room- und Voice-Verbindung dürfen technisch getrennte Protokollverbindungen bleiben.
Sie gehören jedoch demselben Prozess und Lifecycle. Ein Verlust der Room-Verbindung
muss nicht sofort laufendes Audio abbrechen; Readiness und Reconnect-Verhalten werden
aber gemeinsam sichtbar gemacht.

### Wake Word und Agent-Turn

1. Der Wake-Word-Detector erkennt das konfigurierte Wort im Audio-Input des Raums.
2. Die Voice-Runtime startet einen Turn auf der bereits raumgebundenen Voice-Session.
3. Das Gateway transkribiert das Audio.
4. `VoiceTurnService` liest `voice_session.room_id`.
5. Es startet den Conversation-Turn mit einem typisierten `AgentTurnContext` für
   diesen Raum.
6. `TurnWorker` reicht denselben Kontext in `AgentRunRequest` und die turngebundenen
   Dependencies weiter.
7. TTS-Audio wird über den Audio-Output desselben Raums ausgegeben.

### Lokale Seiteneffekte

Die Voice-Lifecycle-Ereignisse werden lokal auf Room-Verhalten abgebildet:

| Voice-Fakt | Room-Reaktion |
|---|---|
| Voice-Capability bereit | `IDLE`, Wake Word aktiv |
| Wake Word erkannt | optionales Wake-Signal; Audio-Fokus anfordern |
| User-Turn gestartet | `LISTENING` |
| Transkript final / Agent arbeitet | `THINKING` |
| Assistant-Audio startet | `SPEAKING` |
| Follow-up wartet | `LISTENING` |
| Konversation beendet | Audio-Fokus freigeben, `IDLE` |
| fataler Voice-Fehler | Fokus freigeben, Capability nicht ready, Fehler melden |

Die Zustandsänderung geht über einen Room-Application-Service. Dieser aktualisiert
das lokale Modell, meldet den Zustand über die bestehende Room-Verbindung und
informiert die Embodiments. Die Voice-Runtime steuert Hue oder Sonos nicht direkt.

### Shutdown

Beim Shutdown beendet der Room-Client in dieser Reihenfolge:

1. keine neuen Activations mehr annehmen;
2. laufenden Voice-Turn kontrolliert abbrechen beziehungsweise schließen;
3. Audio-Fokus und Embodiment wiederherstellen;
4. Voice-Backend und Hardware-Ressourcen schließen;
5. Room-Verbindung schließen.

Alle Schritte sind idempotent, damit partieller Startup und Verbindungsfehler sicher
aufgeräumt werden können.

## 9. Gateway-Verträge und Persistenz

Erforderliche Vertragsänderungen:

- `room: str` wird ohne Kompatibilitätsalias vollständig zu `room_id: UUID`
  umbenannt.
- REST- und RPC-Clients werden aus dem aktualisierten Gateway-Schema neu generiert.
- `VoiceDelivery.room` wird zu `room_id: UUID`.
- Alarm- und Automation-Schemas verwenden für Voice-Delivery eine UUID.
- Filter wie `GET /v1/voice-sessions?room_id=...` sind ebenfalls typisiert.
- Logs und Telemetrie verwenden `cara.room.id`; Room-IDs gehören nicht in
  Span-Namen.

Persistenzmigration:

- `voice_sessions.device_id` beziehungsweise das aktuelle `room`-Mapping wird in
  `room_id` umbenannt und als UUID gespeichert;
- der Unique Index wird zu `uq_voice_sessions_open_room`;
- Automation-/Alarm-Delivery-Spalten werden auf Room-UUIDs migriert;
- `gateway_sessions` erhält ausdrücklich keine Room- oder Metadata-Spalte.

Da bestehende freie Room-Strings nicht verlässlich in UUIDs übersetzt werden
können, muss die Migration entweder eine explizite Zuordnung erhalten oder alte
lokale Entwicklungsdaten verwerfen. Eine stillschweigende Zuordnung anhand des
Display-Namens ist nicht zulässig.

## 10. Readiness und Beobachtbarkeit

Die bestehende Room-Readiness wird um Teilzustände erweitert. Mindestens sichtbar
sind:

- Room beim Gateway registriert;
- Room-Verbindung aktiv;
- konfigurierte Geräte geöffnet;
- Voice-Backend verbunden;
- Wake-Word-Activation aktiv, sofern konfiguriert;
- Audio-Input und Audio-Output verfügbar;
- optionale Embodiments und Audio-Fokus-Adapter mit ihrem Status.

`/ready` ist nur erfolgreich, wenn alle als zwingend konfigurierten Capabilities
bereit sind. Optionale Embodiments dürfen degradiert sein, ohne Voice insgesamt zu
blockieren. `/room` und `/devices` zeigen den Grund einer Degradierung, ohne Secrets
oder Provider-Credentials auszugeben.

Relevante Logs und Traces enthalten `room_id`, `voice_session_id`, `voice_turn_id`
und `session_id` als getrennte strukturierte Felder. Damit bleibt nachvollziehbar,
dass der Room-Kontext aus der Voice-Session stammt und nicht Teil der Conversation-
Session ist.

## 11. Umsetzungsschnitte

### Slice 1: Typisierte Room-ID im Gateway

- `VoiceSession.room` zu `VoiceSession.room_id: UUID` migrieren.
- REST-Schemas, Mapper, Repository und Indizes anpassen.
- Room beim Öffnen einer Voice-Session über `RoomRegistryService` validieren.
- `VoiceDelivery` sowie Alarm-/Automation-Pfade auf UUID umstellen.
- Clients neu generieren und kleinste relevante Gateway-Test-Suites ausführen.

Dieser Slice ändert noch nicht die lokale Prozessstruktur, schafft aber einen
eindeutigen End-to-End-Vertrag.

### Slice 2: Turngebundener Agent-Kontext

- `RoomContext` und `AgentTurnContext` als typisierte Application-Value-Objects
  einführen.
- Optionale Context-Parameter durch `TurnWorker` und `AgentRunRequest` reichen.
- `VoiceTurnService` für initiale, Follow-up- und proaktive Turns anbinden.
- Turn-Dependencies so anpassen, dass sie den aktuellen Context verwenden und nicht
  einen beim Agent-Aufbau gecachten Context.
- Reminder-Delivery auf den expliziten Voice-Room-Kontext umstellen.

Schützenswertes Verhalten: Text-Turn ohne Context, Voice-Turn mit korrekter UUID und
kein Context-Leak zwischen Turns.

### Slice 3: Voice-Runtime in den Room-Client einbetten

- Room-Client vom `voice`-Package abhängig machen.
- Voice-Engine hinter einer Room-Application-Komponente komponieren.
- Room-Lifespan um Start, Reconnect und Shutdown der Voice-Capability erweitern.
- Hardware aus der Room-Konfiguration injizieren.
- separaten `cara-voice`-Entrypoint und dessen Composition Root erst entfernen, wenn
  der Room-Entrypoint denselben Funktionsumfang besitzt.

### Slice 4: Audio-Fokus und Embodiment dem Raum übergeben

- Sonos-Pause/Ducking als `RoomAudioFocus` hinter den raumeigenen Speaker-Adapter
  verschieben.
- Hue und Earcons als `RoomEmbodiment`-Adapter anbinden.
- Voice-Lifecycle auf Room-State und kleine Embodiment-Ereignisse abbilden.
- direkte Hardware-Erzeugung und konkrete Integrationen aus der Voice-Factory
  entfernen.

### Slice 5: Konfiguration und Bereinigung

- `voice.yml` in `room.yml` migrieren.
- doppelte Voice-Hardwaremodelle und freie Room-Strings entfernen.
- Dokumentation und Beispielkonfiguration aktualisieren.
- alte APIs vollständig umbenennen; keine Kompatibilitätsaliasse stehen lassen.

## 12. Akzeptanzkriterien

Die Integration ist abgeschlossen, wenn:

1. Ein Room-Client mit Voice-Konfiguration registriert genau einen Raum und öffnet
   genau eine Voice-Session mit derselben UUID.
2. Ein Wake Word in Raum A startet einen Voice-Turn, dessen Agent-Ausführung einen
   typisierten `RoomContext(room_id=A)` erhält.
3. Ein normaler Text-Turn erhält keinen Room-Kontext; die Conversation-Session
   speichert keine `room_id`.
4. Follow-up- und proaktive Voice-Turns behalten die Room-ID ihrer Voice-Session.
5. Zwei Room-Clients können gleichzeitig jeweils eine eigene offene Voice-Session
   besitzen; zwei offene Voice-Sessions für denselben Raum werden abgelehnt.
6. Reminder oder andere raumbezogene Turn-Dependencies verwenden die explizite
   Room-ID des Voice-Turns und suchen sie nicht heuristisch über aktive Sessions.
7. Mikrofon, Speaker, Sonos und Hue werden nur in `room.yml` konfiguriert.
8. Wake Word erscheint als verfügbare Room-Capability nur, wenn Detector und
   Audio-Input erfolgreich gestartet sind.
9. Voice-Zustände werden über den Room gemeldet und können durch unterschiedliche
   Embodiment-Adapter dargestellt werden.
10. Sonos-Ducking oder -Pause wird bei normalem Ende, Abbruch, Fehler und Shutdown
    sicher zurückgenommen.
11. STT und TTS bleiben im Gateway; der Room-Client benötigt keine Provider-Secrets.
12. In Domain und Application Code wird Room-Kontext nicht als untypisierte
    Metadata-Map transportiert.

## Architekturentscheidungen

- **Die Room-ID lebt auf der Voice-Session.** Sie lebt nicht auf der allgemeinen
  Conversation-Session.
- **Der Agent-Kontext ist turngebunden.** Er wird am Voice-Orchestrator explizit aus
  der Voice-Session erzeugt.
- **Der Room-Client besitzt lokale Hardware.** Die Voice-Engine orchestriert sie nur
  über injizierte Ports.
- **Wake Word ist eine zusammengesetzte Room-Capability.** Es ist keine Eigenschaft
  des Gateway-Agenten und keine elementare Mikrofon-Capability.
- **Embodiment ist technologieoffen.** Hue ist ein Adapter, nicht die Abstraktion.
- **Audio-Fokus ist Room-Medienkoordination.** Er ist vom Embodiment getrennt.
- **STT und TTS bleiben Gateway-seitig.** Die Integration ändert Ownership und
  Kontextfluss, nicht die bestehende Provider-Grenze.
- **Andere Eingabegeräte bleiben außerhalb des Scopes.** Aus dieser Spec entsteht
  kein allgemeines Device-Provenance-Modell für Conversation-Sessions.
