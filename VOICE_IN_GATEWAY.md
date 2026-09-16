# Voice als Gateway-Feature

## Zielbild

Der Voice-Client soll langfristig ein schlanker **Device-/Media-Client** sein. Er
besitzt Mikrofon, Lautsprecher und alles, was nur am konkreten Gerät sinnvoll
entschieden werden kann. Das Gateway besitzt dagegen die sprachliche Session:
Speech-to-Text, Conversation-Turn, Text-to-Speech, die öffentlichen Events und
den persistierten Zustand einer laufenden Voice-Conversation.

Damit wird Voice zu einer echten Eingangs- und Ausgangsmodalität des Gateways
und nicht länger zu einem Client, der eine Textschnittstelle als Transport für
ein lokal erzeugtes Transkript benutzt.

```text
Voice client (device edge)                Gateway
----------------------------------        -------------------------------
microphone / audio buffering       PCM -> voice media ingress
wake word / local activation              STT + transcript stream
local acoustic echo cancellation          voice/conversation coordination
barge-in detection                 ctl -> turn cancellation / steering
speaker playback                  PCM <- TTS + assistant audio stream
device integrations                       persistence + REST + fan-out
```

Das Gateway soll dabei **keine Soundkarte und kein lokales Audiogerät kennen**.
Es verarbeitet Streams und fachliche Voice-Sessions. Der Client adaptiert diese
Streams an seine Hardware.

## Kurzentscheidung

Aus `clients/voice/src/voice` kann konzeptionell ungefähr ein Drittel direkt
oder in überarbeiteter Form ins Gateway wandern. Ein weiteres kleines Drittel
wird durch einen deutlich kleineren Gateway-Media-Adapter im Client ersetzt.
Die hardware- und latenznahe Hälfte muss im Client bleiben.

| Bereich | Ziel | Begründung |
| --- | --- | --- |
| `stt/` | Gateway | Providerzugang, Transkriptionszustand und finale Transkription sind serverseitige Fähigkeiten. |
| `tts/` | Gateway | TTS konsumiert ohnehin den serverseitigen Textstrom und kann Audio direkt über den Media-Socket ausgeben. |
| `llm/` | entfällt | `GatewayAgentSession` (`llm/gateway.py`) repariert heute im Client die Grenze zwischen Voice- und Conversation-Events. Diese Kopplung gehört serverseitig. |
| `handler/command.py` | Gateway | Aus finaler Transkription einen Conversation-Turn zu starten ist fachliche Orchestrierung. |
| Teile aus `handler/turn.py` | Gateway | Voice-Turn-Identität, Status und Kopplung an den Conversation-Turn gehören ins Voice-Feature. |
| Speech-Ressourcen aus `handler/session_lifecycle.py` | Gateway | Das Gateway besitzt künftig STT-/TTS-Verbindungen und deren Lebenszyklus. |
| Voice-Session-/Turn-Zustand | Gateway, persistiert | Laufende Voice-Conversations sind nach Reconnect und für andere Clients per REST abrufbar. |
| `audio/` | Client | Aufnahme, Playback, Pufferung, PortAudio und Sonos sind Gerätefunktionen. |
| `echo_cancellation/` | Client | Echo Cancellation braucht das tatsächlich ausgegebene Signal und das lokale Mikrofontiming. |
| `wakeword/` und Wake-Word-Aktivierung | Client | Lokale Erkennung vermeidet permanenten Netzwerk-Upload und bleibt bei Netzstörungen verfügbar. |
| `barge_in/` Signalerkennung | Client | Wake Word, VAD und akustischer Kontext sind lokal; das Resultat wird als Gateway-Kommando gesendet. |
| `AudioBridge`/Playback | Client, stark vereinfacht | Empfängt Gateway-Audio und schreibt es mit begrenztem Puffer auf das gewählte Ausgabegerät. |
| `lights/`, `playback/`, `sound.py`, Sonos-Fokus | Client | Reaktionen auf lokale Geräte und LAN-Ressourcen bleiben Edge-Verantwortung. |
| `conversation/` Audioaufnahme | Client, vorerst | Serverseitige Aufzeichnung über Object Storage folgt später (siehe [Später: Audioaufzeichnung](#später-audioaufzeichnung-über-object-storage)). |
| Integrationen für reine UI-/Gerätezustände | Client | Das Gateway liefert Lifecycle-Events, der Client entscheidet über lokale Effekte. |

Das erwartete Endergebnis ist kein leerer Client. Ein Voice-Client braucht
weiterhin substanzielle Echtzeit- und Hardwarelogik. Er sollte aber keine
Deepgram-Zugangsdaten, keine Agent-Session-Abstraktion und keine eigene
semantische Turn-Pipeline mehr besitzen.

## Verantwortungsgrenze

### Gateway: neues Feature `gateway.features.voice`

Das Feature besitzt:

- Voice-Session und Voice-Turn als persistierte fachliche Zustände;
- Zuordnung von Voice-Session zu Conversation-Session und Voice-Turn zur
  erzeugten User-Message;
- serverseitige STT- und TTS-Ports sowie Provideradapter;
- Streaming von partiellen und finalen Transkriptionen;
- Start eines Conversation-Turns aus der finalen Transkription;
- Streaming der Assistant-Texte in TTS und Ausgabe der Audio-Chunks;
- Abbruch, Barge-in und Fehlerzustände;
- Ownership des Media-Streams und Fan-out der Voice-Events;
- REST-Routen zum Öffnen, Schließen und Abrufen von Voice-Sessions.

Struktur analog zu `alarm` und `conversation`:

```text
gateway/src/gateway/features/voice/
├── feature.py
├── domain/
│   ├── voice_session.py      # Aggregate: Status, Formate, Device-Owner
│   ├── voice_turn.py         # Entity: Zustandsmaschine, Transkript, Fehler
│   ├── values.py             # AudioFormat, Activation, VoiceTurnStatus
│   ├── errors.py
│   └── repository.py         # VoiceSessionRepository (ABC)
├── application/
│   ├── ports.py              # SpeechToText, TextToSpeech (ABCs)
│   ├── voice_session_service.py
│   └── voice_turn_service.py # Orchestrierung STT -> conversation -> TTS
├── infrastructure/
│   ├── orm.py                # voice_sessions, voice_turns
│   ├── repository.py
│   ├── deepgram_stt.py
│   ├── deepgram_tts.py
│   └── provider.py
└── presentation/
    ├── router.py             # REST /v1/voice-sessions
    ├── schemas.py
    ├── mapper.py
    ├── errors.py
    ├── rpc/                  # voice.turn.* und voice.event
    └── media/                # binärer Media-WebSocket
```

Das Voice-Feature darf `conversation.application` benutzen. Conversation darf
umgekehrt Voice nicht importieren. Voice ist eine Modalitätsintegration, die
einen normalen Conversation-Turn startet und dessen Events konsumiert.

### Client: `voice_edge`

Der verbleibende Client besitzt:

- `AudioInput` und `AudioOutput`;
- kontinuierlichen Ringpuffer und Pre-Roll;
- Wake-Word-Erkennung und lokale Aktivierungsquellen;
- Echo Cancellation und lokale VAD-/Barge-in-Signale;
- Media-Transport mit Backpressure und Reconnect;
- Wiedergabe der Assistant-Audio-Chunks;
- lokale Integrationen wie Hue, Sonos-Fokus, Earcons und vorerst Recording.

Seine Kernschleife wird damit ungefähr:

```text
REST   open or resume voice session
media  connect /v1/voice-sessions/{id}/media
rpc    subscription.subscribe(session_id)
REST   GET voice session snapshot (Reconnect-Zustand)

wait for local activation
  -> rpc   voice.turn.start
  -> media upload buffered pre-roll + live microphone frames
  -> rpc   receive transcript/lifecycle events
  -> media receive and play assistant audio frames
  -> rpc   voice.turn.playback_completed or voice.turn.interrupt
```

## Transportaufteilung

Es gilt die Regel aus `docs/gateway-transport.md`: **WebSocket-RPC nur für
Zustand, der an eine lebende Verbindung oder einen aktiven Turn gebunden ist.
Alles andere ist REST.** Für Voice kommt als dritte Ebene ein binärer
Media-Socket hinzu, weil Audio weder in REST noch in JSON-RPC gehört.

| Operation | Transport | Begründung |
| --- | --- | --- |
| Voice-Session öffnen, auflisten, abrufen, schließen | REST | Persistierte Ressource, unabhängig von einer Verbindung; Snapshot für Initial-Load und Reconnect. |
| Voice-Turn inkl. Transkript und Status abrufen | REST | Lesender Zugriff auf persistierten Zustand. |
| `voice.turn.start` | RPC | Öffnet einen aktiven Turn; Ergebnis kommt ohnehin als Events auf dem Socket. |
| `voice.turn.interrupt` | RPC | Steuert einen laufenden Turn und darf nicht hinter Audio warten. |
| `voice.turn.playback_completed` | RPC | Bestätigung zum aktiven Turn durch den Ausgabe-Owner. |
| Notification `voice.event` | RPC | Fan-out über die bestehende Session-Subscription. |
| Mikrofon- und Assistant-Audio, Input-Ende | Media-WebSocket | Hochfrequenter Bytestrom mit Reihenfolge relativ zu den Audioframes. |

Beim Implementieren werden die Voice-Einträge in `docs/gateway-transport.md`
ergänzt und beide Clients über `scripts/codegen/generate_gateway_clients.sh`
neu generiert (REST: `GatewayRestClient`, RPC: `GatewayRpcClient`). Der
Media-Socket ist bewusst **nicht** Teil der generierten Clients.

## Nicht Audio durch JSON-RPC tunneln

Der vorhandene Gateway-WebSocket liest und schreibt JSON. Binärdaten würden
deshalb als Base64 im JSON landen. Das ist für gelegentliche WAV-Earcons
akzeptabel, aber nicht für einen dauerhaften Vollduplex-Mediastream:

- Base64 vergrößert die Nutzlast um ungefähr ein Drittel;
- jedes kleine Frame verursacht JSON-, Modellvalidierungs- und RPC-Overhead;
- Control-Nachrichten können hinter Audio-Chunks warten;
- Backpressure, Drop-Regeln und Stream-Ende sind im Request/Response-Modell
  schlecht ausdrückbar;
- generierter OpenRPC-Clientcode ist nicht der richtige Abstraktionsort für
  einen hochfrequenten Bytestrom.

Deshalb **ein Gateway, drei Protokollebenen**: REST für Ressourcen, der
bestehende JSON-RPC-Socket für Turn-Control und Events, ein eigener binärer
Media-Socket pro Voice-Session. Multiplexing von Binary-Frames über
`/v1/gateway` würde RPC-Transport, Clientgenerator und Media-Framing koppeln und
ist für den ersten Ausbau nicht vorgesehen.

## Öffentlicher Vertrag

Die Namen sind ein Entwurf; entscheidend sind die getrennten Konzepte.

### REST

Router `voice_router` mit `CanonRouter`, `DishkaRoute` und
`dependencies=[Depends(require_token)]` wie alle Resource-Router.

```text
POST /v1/voice-sessions                                   -> 201 VoiceSessionResponse
GET  /v1/voice-sessions?session_id=&room=&status=         -> VoiceSessionListResponse
GET  /v1/voice-sessions/{voice_session_id}                -> VoiceSessionSnapshotResponse
POST /v1/voice-sessions/{voice_session_id}/close          -> VoiceSessionResponse
GET  /v1/voice-sessions/{voice_session_id}/turns/{voice_turn_id} -> VoiceTurnResponse
```

`POST /v1/voice-sessions`:

```json
{
  "session_id": "…",
  "room": "kitchen",
  "input_formats": [{ "encoding": "pcm_s16le", "sample_rate": 16000, "channels": 1 }],
  "output_formats": [{ "encoding": "pcm_s16le", "sample_rate": 24000, "channels": 1 }]
}
```

Die Antwort enthält die ausgehandelten Formate und `media_path`
(`/v1/voice-sessions/{id}/media`). Pro `room` gibt es höchstens eine offene
Voice-Session; ein zweites Öffnen liefert `409 VOICE_SESSION_ALREADY_OPEN` mit
der ID der bestehenden. Nach einem Reconnect sucht der Client seine Session über
`GET /v1/voice-sessions?room=…&status=open`.

`GET /v1/voice-sessions/{id}` liefert den Snapshot:

```json
{
  "voice_session": {
    "id": "…",
    "session_id": "…",
    "room": "kitchen",
    "status": "open",
    "input_format": { "encoding": "pcm_s16le", "sample_rate": 16000, "channels": 1 },
    "output_format": { "encoding": "pcm_s16le", "sample_rate": 24000, "channels": 1 },
    "media_path": "/v1/voice-sessions/…/media",
    "media_connected": true,
    "created_at": "…",
    "closed_at": null,
    "close_reason": null
  },
  "turns": [
    {
      "id": "…",
      "index": 3,
      "activation": "wake_word",
      "status": "speaking",
      "transcript": "Wie wird das Wetter morgen?",
      "user_message_id": "…",
      "error": null,
      "started_at": "…",
      "input_ended_at": "…",
      "transcribed_at": "…",
      "speech_started_at": "…",
      "ended_at": null
    }
  ],
  "active_turn_id": "…",
  "last_sequence": 41
}
```

Assistant-Text wird **nicht** im Voice-Turn dupliziert. Wer Antworten und
Tool-Calls braucht, lädt `GET /v1/sessions/{session_id}`; der Voice-Turn
verweist über `user_message_id` auf den Einstieg in die Conversation.

`close` beendet einen laufenden Voice-Turn als `cancelled`, trennt den
Media-Socket und setzt `close_reason = "client"`. Geschlossene Voice-Sessions
bleiben abrufbar.

Diskriminierte Unions in den Schemas deklarieren ihren Tag ohne Default (siehe
httpxgen-Hinweis in `docs/gateway-transport.md`).

### RPC-Methoden (`/v1/gateway`)

```text
voice.turn.start(voice_session_id, activation, pre_roll_sequence?)
  -> { voice_session_id, voice_turn_id }
voice.turn.interrupt(voice_turn_id, input_sequence?)
  -> { voice_session_id, voice_turn_id }
voice.turn.playback_completed(voice_turn_id)
  -> { voice_session_id, voice_turn_id }
```

`voice.turn.start` startet noch keinen Conversation-Turn mit einem leeren oder
künstlichen Text. Es legt einen Voice-Turn im Status `listening` an und öffnet
den STT-Stream. Erst die finale, normalisierte Transkription erzeugt
serverseitig User-Message und Conversation-Turn.

Es gibt bewusst **kein** `voice.turn.end_input`: Das Input-Ende muss relativ zum
letzten Audioframe geordnet sein und ist deshalb ein Media-Frame.

Fehler: `ResourceNotFoundError`, `VoiceTurnAlreadyActiveError`,
`MediaNotConnectedError`, `NotMediaOwnerError`, `TurnAlreadyRunningError`
(Conversation-Session bereits durch einen anderen Turn belegt).

### Events

Voice-Events laufen als Notification `voice.event` über dieselbe
`subscription.subscribe(session_id)` wie `session.event`. Ein Client, der eine
Conversation-Session abonniert, sieht damit auch deren Voice-Lifecycle.

Nur Lifecycle-Fakten, die Clients tatsächlich konsumieren, werden Events. Interne
Übergänge wie `transcribing` oder `waiting_for_assistant` stehen im persistierten
Status und sind per REST sichtbar, werden aber nicht einzeln publiziert.

```text
voice.turn.started
voice.transcript.partial          # flüchtig
voice.transcript.final            # enthält user_message_id
voice.assistant_audio.started
voice.assistant_audio.completed   # Gateway hat den letzten Frame gesendet
voice.turn.completed              # nach playback_completed
voice.turn.discarded              # keine Sprache erkannt, kein Conversation-Turn
voice.turn.cancelled
voice.turn.failed
voice.session.closed
```

Jedes Event trägt `voice_session_id`, `voice_turn_id` (außer
`voice.session.closed`), `session_id`, einen serverseitigen Zeitstempel und eine
pro Voice-Session monotone `sequence`.

`sequence` zählt nur persistierte Lifecycle-Events. `voice.transcript.partial`
trägt stattdessen eine turn-lokale `revision` und ersetzt vorherige Partials
(latest wins). Weil der Snapshot `last_sequence` enthält, kann der Client zuerst
abonnieren, dann den Snapshot laden und Events mit `sequence <= last_sequence`
verwerfen. Damit hat Voice die Lücke nicht, die `docs/gateway-transport.md` für
den Conversation-Snapshot noch beschreibt.

Assistant-Text wird nicht als Voice-Event dupliziert; `chat.delta` und
`chat.completed` bleiben die Quelle für Text und Tool-Calls.

### Media-Socket

```text
WS /v1/voice-sessions/{voice_session_id}/media
```

- Authentisierung wie `/v1/gateway` über `Authorization: Bearer` im Handshake
  (`GatewayAuthenticator.authenticate`). Kein Token als Query-Parameter.
- Genau eine Media-Verbindung pro Voice-Session; sie ist Input- und
  Output-Owner. Eine zweite Verbindung wird mit `1008` abgewiesen.
- Verbindungsabbruch: ein aktiver Voice-Turn endet als `cancelled`
  (`media_disconnected`), die Voice-Session bleibt für ein konfigurierbares
  Reconnect-Fenster offen und schließt danach mit
  `close_reason = "media_timeout"`.

Frames tragen einen kleinen binären Header:

```text
version | kind | voice_turn_index | sequence | timestamp_ms | payload_length | payload
```

`kind` unterscheidet `input_pcm`, `input_end`, `output_pcm` und `output_end`.
Audioformat und Codec werden beim Öffnen der Voice-Session ausgehandelt, nicht
in jedem Chunk wiederholt. Für den ersten Schritt reicht PCM S16LE mono. Opus
kann später ergänzt werden, ohne das fachliche API zu verändern.

Für Mikrofonframes gilt eine begrenzte Queue. Ist der Upstream dauerhaft zu
langsam, endet der Turn mit einem expliziten `input_overrun`; alte
Sprachaudioframes dürfen nicht stillschweigend minutenlang nachlaufen. Für
Assistant-Audio erzeugt der TTS-Consumer durch seine begrenzte Queue
Backpressure bis zum Provider.

## Persistenz einer laufenden Voice-Conversation

Eine laufende Voice-Conversation wird **fortlaufend** in der bestehenden
Gateway-Datenbank gespeichert, nicht erst am Ende. Dadurch kann ein Client nach
einem Reconnect, ein zweiter beobachtender Client oder ein Debugging-Werkzeug
den autoritativen Zustand jederzeit per REST abrufen.

### Tabellen

```text
voice_sessions
  id, session_id -> sessions.id, room, status (open | closed),
  input_format, output_format, last_sequence,
  created_at, closed_at, close_reason

voice_turns
  id, voice_session_id -> voice_sessions.id, index,
  activation (wake_word | manual | follow_up | barge_in | proactive),
  status, transcript, user_message_id, stt_provider, tts_provider,
  error_code, error_message,
  started_at, input_ended_at, transcribed_at, speech_started_at, ended_at
```

Persistiert werden Metadaten, finale Transkripte und Verweise. **Nicht**
persistiert werden partielle Transkripte, Assistant-Text (liegt bereits in der
Conversation) und Rohaudio.

### Schreibzeitpunkte

| Auslöser | Schreibvorgang | Event |
| --- | --- | --- |
| `POST /v1/voice-sessions` | `voice_sessions` anlegen | — |
| `voice.turn.start` | Turn `listening` anlegen | `voice.turn.started` |
| `input_end` oder STT-Endpointing | `transcribing`, `input_ended_at` | — |
| finale Transkription, nicht leer | User-Message über `TurnService` anlegen, dann `transcript`, `user_message_id`, `waiting_for_assistant` | `voice.transcript.final` |
| finale Transkription, leer | `discarded` | `voice.turn.discarded` |
| erster TTS-Frame gesendet | `speaking`, `speech_started_at` | `voice.assistant_audio.started` |
| letzter TTS-Frame gesendet | — | `voice.assistant_audio.completed` |
| `voice.turn.playback_completed` | `completed`, `ended_at` | `voice.turn.completed` |
| Interrupt, Conversation-Turn abgebrochen, Media-Abbruch | `cancelled` | `voice.turn.cancelled` |
| STT-/TTS-/Conversation-Fehler | `failed`, `error_*` | `voice.turn.failed` |

Status und `last_sequence` werden in derselben Transaktion geschrieben und erst
danach wird das Event publiziert. Ein Turn hat damit höchstens etwa sechs
Schreibvorgänge, was für SQLite unkritisch ist.

Beim Gateway-Start werden alle nicht-terminalen Voice-Turns als `failed`
(`gateway_restarted`) und alle offenen Voice-Sessions als `closed` markiert. Ein
Media-Stream kann einen Neustart nicht überleben, ein persistierter
`speaking`-Status wäre danach eine Lüge.

### Herkunft der User-Message

Der Voice-Client übergibt heute `{"modality": "voice"}` als Turn-Metadaten. Diese
landen nicht an der persistierten `UserMessage`. Statt Conversation um
Voice-Felder zu erweitern, liegt die Herkunft im Voice-Feature: `voice_turns`
verweist per `user_message_id` auf die Nachricht. Conversation bleibt
Voice-agnostisch; wer wissen will, ob eine Nachricht gesprochen wurde, fragt das
Voice-Feature.

## Turn-Zustandsmodell

Voice-Turn und Conversation-Turn sind nicht identisch:

```text
listening
  -> transcribing
  -> waiting_for_assistant   (ab hier existiert user_message_id)
  -> speaking
  -> completed

transcribing -> discarded
jeder aktive Zustand -> cancelled | failed
```

Diese Trennung löst das heutige Problem der Textschnittstelle. Eine
fehlgeschlagene oder leere Aufnahme erzeugt keinen Conversation-Turn. Ein
Text-Client startet weiterhin direkt einen Conversation-Turn. Ein Voice-Client
startet zuerst einen Voice-Turn, aus dem optional genau ein Conversation-Turn
entsteht.

Proaktive Conversation-Turns (Alarme, Automationen über `start_scheduled`) für
eine Conversation-Session mit offener Voice-Session erzeugen einen Voice-Turn
mit `activation = "proactive"`, der direkt in `waiting_for_assistant` beginnt
und damit dieselbe TTS- und Playback-Strecke nutzt.

`playback_completed` ist eine Bestätigung des Media-Owners. Erst dann kann das
Gateway eine serverseitige Follow-up-Policy starten. Verliert der Client die
Verbindung, endet der Turn als `cancelled`, statt eine Wiedergabe anzunehmen.

## Barge-in und niedrige Latenz

Barge-in wird geteilt:

- Der Client erkennt das lokale Signal (Wake Word oder Sprache trotz Echo
  Cancellation) und stoppt die Wiedergabe sofort.
- Parallel sendet er `voice.turn.interrupt` an das Gateway.
- Das Gateway bricht TTS und über `TurnService.cancel` den zugehörigen
  Conversation-Turn ab und markiert den Voice-Turn als `cancelled`.
- Der Client startet einen neuen Voice-Turn mit `activation = "barge_in"` und
  sendet Pre-Roll ab der gemeldeten lokalen Sequenznummer.

Das lokale Stoppen darf nicht auf die Netzwerkantwort warten. Der Gateway-
Abbruch bleibt trotzdem autoritativ für den persistierten Zustand.

## Nötige Änderungen an bestehendem Gateway-Code

- **User-Message-ID aus `TurnService.start`:** `start` gibt heute nichts zurück;
  die ID der persistierten `UserMessage` entsteht erst im Hintergrund-Task
  `_execute`. Voice braucht sie für `user_message_id`. Die User-Message sollte
  deshalb vor dem Task angelegt und ihre ID zurückgegeben werden.
- **In-Process-Konsum von Conversation-Events:** Die einzige
  `EventPublisher`-Implementierung ist `InMemoryEventStream` in
  `presentation/websocket/subscriptions.py` und verteilt nur an WebSocket-Clients.
  Voice muss `chat.delta`, `chat.completed` und die Terminal-Events aber
  serverseitig konsumieren. Dafür braucht `conversation.application` eine
  abonnierbare Event-Quelle (ABC) mit Fan-out-Implementierung in der
  Infrastruktur; der WebSocket-Forwarder wird einer ihrer Konsumenten. Voice
  darf nicht aus `presentation` importieren.
- **Voice-Events im Subscription-Fan-out:** `EventReceiver` transportiert heute
  nur `ConversationEvent`. Er muss auch Voice-Events für die abonnierte
  Conversation-Session ausliefern, damit `voice.event` ohne zweite
  Subscription-Verwaltung funktioniert.
- **Doku und Clients:** `docs/gateway-transport.md` um die Voice-Zeilen ergänzen,
  Schemas exportieren und Clients neu generieren.

## Konfiguration und Secrets

Nach der Migration liegen STT-/TTS-Provider, Modelle, Sprache, Timeouts,
Reconnect-Fenster und Provider-Secrets in der Gateway-Konfiguration. Im Client
verbleiben nur:

- Gateway-Adresse und Authentisierung;
- `room`, Raumwahl und lokale Audioformate;
- Wake Word, VAD, Echo Cancellation und Barge-in-Einstellungen;
- lokale Ausgabe-, Integrations- und Recording-Einstellungen.

Das ist ein wesentlicher Gewinn des Umbaus: neue Voice-Clients benötigen keine
Provider-SDKs und keine Provider-Zugangsdaten.

## Migrationsplan

### Phase 1: Ressourcen, Persistenz und serverseitiges TTS

- `gateway.features.voice` mit Domain, `voice_sessions`/`voice_turns` und
  Repository anlegen.
- REST-Routen `/v1/voice-sessions` (öffnen, auflisten, abrufen, schließen).
- In-Process-Event-Quelle in `conversation.application` einführen.
- Media-Socket mit Downstream (`output_pcm`, `output_end`).
- TTS-Port und Deepgram-Adapter ins Gateway verschieben.
- Conversation-Turns einer Session mit offener Voice-Session erzeugen einen
  Voice-Turn (`activation = "proactive"`-Pfad, hier noch für Text von
  `turn.start`); Assistant-Text geht serverseitig in TTS.
- Der Client behält STT vorerst und sendet weiterhin Text an `turn.start`,
  empfängt Audio aber bereits über den Media-Socket und bestätigt per
  `voice.turn.playback_completed`.

Diese Phase erprobt den schwierigeren Downstream-Mediatransport und die
Persistenz, ohne den Inputpfad gleichzeitig umzustellen. Der Pfad für
Gateway-initiierte Turns ist ohnehin für proaktive Turns nötig und damit kein
Übergangscode.

### Phase 2: Audio-Ingress und serverseitiges STT

- Upstream-Frames (`input_pcm`, `input_end`), Sequenzierung und Backpressure.
- STT-Port und Deepgram-Adapter ins Gateway verschieben.
- `voice.turn.start` und `voice.turn.interrupt` als RPC-Methoden.
- `voice.transcript.partial`/`final` publizieren, finale Transkription persistieren.
- `TurnService.start` liefert die User-Message-ID.
- `CommandBridge` und `SpeechToTextBridge` aus dem Client entfernen.

Ab hier wird die Textschnittstelle nicht mehr vom Voice-Client als
Audio-Ersatz benutzt.

### Phase 3: serverseitige Voice-Orchestrierung

- Follow-up-Policy nach `playback_completed` ins Gateway verschieben.
- Reconnect-Fenster und Neustart-Bereinigung.
- `GatewayAgentSession`, große Teile der Handler und deren parallelen lokalen
  Voice-Zustand entfernen.
- Client-API auf REST-Voice-Session, RPC-Turn-Control und `MediaTransport`
  reduzieren.

### Phase 4: weitere Clients und Aufzeichnung

- Browser-/Mobile-Clients über denselben Vertrag anbinden. Browser können im
  WebSocket-Handshake keinen `Authorization`-Header setzen; dafür kommt ein
  kurzlebiger, an Voice-Session und Richtung gebundener Media-Token per REST
  (`POST /v1/voice-sessions/{id}/media-tokens`) hinzu.
- Audioaufzeichnung über Object Storage (nächster Abschnitt).
- Erst bei Bedarf Opus und Handover zwischen Geräten ergänzen.

## Später: Audioaufzeichnung über Object Storage

Vorerst wird **kein** Audio im Gateway gespeichert; die Aufnahme bleibt im
Client (`ConversationAudioRecorder` und `ConversationAudioMixer` in
`clients/voice/src/voice/conversation`). Wenn serverseitige Aufzeichnung dazukommt,
gilt Folgendes.

### Grundlage

`gateway.platform.storage` stellt bereits `ObjectStorage` (ABC) mit
`S3ObjectStorage` auf Basis von obstore bereit, inklusive `get_signed_url` und
getrenntem `public_endpoint_url` für signierte URLs. Es ist aber noch nirgends
verdrahtet. Nötig sind:

- Storage-Settings (`bucket`, `endpoint_url`, `public_endpoint_url`,
  Zugangsdaten) in der Gateway-Konfiguration;
- ein Dishka-Provider für `ObjectStorage` in `platform_feature`;
- Audio-Typen in `ContentType`, mindestens `audio/wav` und später `audio/ogg`.

### Ablage

`ObjectStorage.upload_bytes` schreibt nur vollständige Objekte. Deshalb schreibt
der Media-Ingress segmentweise, etwa alle paar Sekunden pro Spur:

```text
voice/{voice_session_id}/{voice_turn_id}/input/{segment:06d}.pcm
voice/{voice_session_id}/{voice_turn_id}/output/{segment:06d}.pcm
```

Nach Turn-Ende werden die Segmente zu `input.wav` und `output.wav`
zusammengesetzt und der Segmentordner per `delete_folder` entfernt.
Alternativ bekommt `ObjectStorage` einen Streaming-Upload (obstore unterstützt
Multipart); das wird bei der Umsetzung entschieden.

Eine gemischte Gesprächsaufnahme übernimmt die Logik des Client-
`ConversationAudioMixer`, verwendet aber die `timestamp_ms` aus den Frame-Headern
statt der Ankunftszeit. Das Mikrofonsignal ist bereits echo-bereinigt, weil
AEC im Client bleibt.

### Persistenz und Retention

- Aufzeichnung ist Opt-in: Gateway-Default aus, pro Voice-Session beim Öffnen
  anforderbar (`record: true`).
- Tabelle `voice_recordings`: `voice_turn_id`, `track` (`input` | `output` |
  `mixed`), `object_path`, `content_type`, `duration_ms`, `size_bytes`,
  `created_at`, `expires_at`. Keine Audio-BLOBs in SQLite.
- Ein Retention-Job löscht abgelaufene Objekte und Zeilen; das Löschen einer
  Voice-Session entfernt `voice/{voice_session_id}/` vollständig.

### REST

```text
GET /v1/voice-sessions/{voice_session_id}/turns/{voice_turn_id}/recordings
  -> Liste der Spuren mit Metadaten
GET /v1/voice-sessions/{voice_session_id}/turns/{voice_turn_id}/recordings/{track}
  -> { "url": "<signed url>", "expires_at": "…" }
```

Das Audio selbst läuft nicht durch das Gateway, sondern über die signierte URL
aus `get_signed_url`. Eine JSON-Antwort statt `307` hält den generierten
REST-Client frei von Redirect-Sonderfällen.

## Was nicht 1:1 verschoben werden sollte

Der lokale `EventBus`, `VoiceChannel` und die Handler bilden heute gemeinsam
eine In-Process-Pipeline. Diese Klassen komplett ins Gateway zu kopieren würde
nur die bestehende Architektur an einen anderen Ort verschieben und parallel
zum bereits vorhandenen Conversation-Lebenszyklus einen zweiten Turn-Manager
erzeugen.

Stattdessen sollten die Provider-Ports und bewährten Streamingmechanismen
übernommen, die Zustandsführung aber als Gateway-Voice-Feature neu modelliert
werden. Insbesondere gilt:

- Gateway-UUIDs statt lokaler Integer-`turn_id`s;
- bestehende Conversation-Events statt eines zweiten Agent-Eventmodells;
- Gateway-DI statt Konstruktion aller Komponenten in `VoiceChannel`;
- REST-, RPC- und Media-Verträge statt In-Process-Requests;
- persistierte fachliche Zustände statt nur laufender Tasks.

## Definition of Done für den schlanken Client

Der Umbau ist erreicht, wenn der Client:

- keine STT-/TTS-Providerabhängigkeit und keine Provider-Secrets mehr besitzt;
- keinen `AgentSession`-Port und kein Mapping von Gateway- auf lokale
  Agent-Events mehr benötigt;
- keinen Conversation-Turn aus einem lokal erzeugten Text startet;
- nur Aktivierung, PCM-Upload, PCM-Playback, lokale Akustik und lokale Geräte
  orchestriert;
- nach einem Reconnect den autoritativen Voice-Zustand über
  `GET /v1/voice-sessions/{id}` und den Conversation-Zustand über
  `GET /v1/sessions/{id}` bezieht;
- durch einen Mock-Gateway (REST, RPC und Media) vollständig ohne Deepgram und
  Agent getestet werden kann.

Damit bleibt der Client dort komplex, wo Echtzeit-Hardware zwangsläufig
komplex ist, und wird dort schlank, wo er heute Gateway-Verantwortung lokal
nachbildet.
