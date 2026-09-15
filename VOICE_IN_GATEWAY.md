# Voice als Gateway-Feature

## Zielbild

Der Voice-Client soll langfristig ein schlanker **Device-/Media-Client** sein. Er
besitzt Mikrofon, Lautsprecher und alles, was nur am konkreten Gerät sinnvoll
entschieden werden kann. Das Gateway besitzt dagegen die sprachliche Session:
Speech-to-Text, Conversation-Turn, Text-to-Speech und die dazugehörigen
öffentlichen Events.

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
device integrations                       persistence + fan-out
```

Das Gateway soll dabei **keine Soundkarte und kein lokales Audiogerät kennen**.
Es verarbeitet Streams und fachliche Voice-Sessions. Der Client adaptiert diese
Streams an seine Hardware.

## Kurzentscheidung

Aus `clients/voice/src/voice` kann konzeptionell ungefähr ein Drittel direkt
oder in überarbeiteter Form ins Gateway wandern. Ein weiteres kleines Drittel
wird durch einen deutlich kleineren Gateway-Media-Adapter im Client ersetzt.
Die hardware- und latenznahe Hälfte muss im Client bleiben.

Die aktuelle Paketgröße liegt bei rund 5.400 Python-Zeilen. Die Zahlen sind nur
eine Größenordnung, weil beim Verschieben insbesondere Event-Bus- und
Orchestrierungscode nicht 1:1 übernommen werden sollte.

| Bereich | Ziel | Begründung |
| --- | --- | --- |
| `stt/` | Gateway | Providerzugang, Transkriptionszustand und finale Transkription sind serverseitige Fähigkeiten. |
| `tts/` | Gateway | TTS konsumiert ohnehin den serverseitigen Textstrom und kann Audio direkt als Gateway-Event ausgeben. |
| `llm/` | größtenteils entfallen/ins Gateway | `GatewayAgentSession` repariert heute im Client die Grenze zwischen Voice-Events und Conversation-Events. Diese Kopplung gehört serverseitig. |
| `handler/command.py` | Gateway | Aus finaler Transkription einen Conversation-Turn zu starten ist fachliche Orchestrierung. |
| Teile aus `handler/turn.py` | Gateway | Voice-Turn-Identität, Status und Kopplung an den Conversation-Turn gehören ins Voice-Feature. |
| Speech-Ressourcen aus `handler/session_lifecycle.py` | Gateway | Das Gateway besitzt künftig STT-/TTS-Verbindungen und deren Lebenszyklus. |
| Öffentliche Transkript-/Assistant-Audio-Events | Gateway-Vertrag | Sie sollen allen berechtigten Clients zur Verfügung stehen, nicht nur dem lokalen EventBus. |
| `audio/` | Client | Aufnahme, Playback, Pufferung, PortAudio und Sonos sind Gerätefunktionen. |
| `echo_cancellation/` | Client | Echo Cancellation braucht das tatsächlich ausgegebene Signal und das lokale Mikrofontiming. |
| `wakeword/` und Wake-Word-Aktivierung | Client | Lokale Erkennung vermeidet permanenten Netzwerk-Upload und bleibt bei Netzstörungen verfügbar. |
| `barge_in/` Signalerkennung | Client | Wake Word, VAD und akustischer Kontext sind lokal; das Resultat wird als Gateway-Kommando gesendet. |
| `AudioBridge`/Playback | Client, stark vereinfacht | Empfängt Gateway-Audio und schreibt es mit begrenztem Puffer auf das gewählte Ausgabegerät. |
| `lights/`, `playback/`, `sound.py`, Sonos-Fokus | Client | Reaktionen auf lokale Geräte und LAN-Ressourcen bleiben Edge-Verantwortung. |
| `conversation/` Audioaufnahme | zunächst Client | Sie benötigt rohe lokale Ein- und Ausgangssamples; serverseitige Archivierung kann später optional ergänzt werden. |
| Observer für reine UI-/Gerätezustände | Client | Das Gateway liefert Zustandsereignisse, der Client entscheidet über lokale Effekte. |

Das erwartete Endergebnis ist kein leerer Client. Ein Voice-Client braucht
weiterhin substanzielle Echtzeit- und Hardwarelogik. Er sollte aber keine
Deepgram-Zugangsdaten, keine Agent-Session-Abstraktion und keine eigene
semantische Turn-Pipeline mehr besitzen.

## Verantwortungsgrenze

### Gateway: neues Feature `gateway.features.voice`

Das Feature besitzt:

- Voice-Session und Voice-Turn als fachliche Zustände;
- Zuordnung von Voice-Turn, Conversation-Session und Conversation-Turn;
- serverseitige STT- und TTS-Ports sowie Provideradapter;
- Streaming von partiellen und finalen Transkriptionen;
- Start eines Conversation-Turns aus der finalen Transkription;
- Streaming der Assistant-Texte in TTS;
- Ausgabe formatierter Assistant-Audio-Chunks;
- Abbruch, Barge-in und Fehlerzustände;
- Berechtigung, Ownership und Fan-out der Voice-Events;
- optional Persistenz von Transkripten und Audio-Objektreferenzen.

Vorgeschlagene Struktur:

```text
gateway/src/gateway/features/voice/
├── domain/
│   ├── session.py
│   ├── turn.py
│   └── values.py
├── application/
│   ├── events.py
│   ├── ports.py          # SpeechToText, TextToSpeech, MediaPublisher
│   └── service.py        # Orchestrierung STT -> conversation -> TTS
├── infrastructure/
│   ├── deepgram_stt.py
│   ├── deepgram_tts.py
│   └── provider.py
└── presentation/
    ├── rpc/              # Control Plane und typisierte Events
    └── media/            # binäre WebSocket-Frames
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
- lokale Observer wie Hue, Sonos-Fokus, Earcons und Recording.

Seine Kernschleife wird damit ungefähr:

```text
wait for local activation
  -> open gateway voice turn
  -> upload buffered pre-roll + live microphone frames
  -> receive transcript/status events
  -> receive and play assistant audio frames
  -> send playback-completed or interrupt
```

## Nicht Audio durch JSON-RPC tunneln

Der vorhandene Gateway-WebSocket liest und schreibt JSON (`receive_json` und
`send_json`). Binärdaten würden deshalb als Base64 im JSON landen. Das ist für
gelegentliche WAV-Earcons akzeptabel, aber nicht für einen dauerhaften
Vollduplex-Mediastream:

- Base64 vergrößert die Nutzlast um ungefähr ein Drittel;
- jedes kleine Frame verursacht JSON-, Modellvalidierungs- und RPC-Overhead;
- Control-Nachrichten können hinter Audio-Chunks warten;
- Backpressure, Drop-Regeln und Stream-Ende sind im Request/Response-Modell
  schlecht ausdrückbar;
- generierter OpenRPC-Clientcode ist nicht der richtige Abstraktionsort für
  einen hochfrequenten Bytestrom.

Empfehlung: **ein Gateway, aber zwei Protokollebenen**.

1. Der bestehende JSON-RPC-WebSocket bleibt der Control Plane für Methoden,
   Zustände und kleine Events.
2. Ein binärer Media-WebSocket am Gateway transportiert Audio in beide
   Richtungen.

Zum Beispiel:

```text
POST/JSON-RPC voice.session.open
  -> voice_session_id, media_url, media_token, negotiated formats

WS /v1/voice/{voice_session_id}/media
  client -> binary microphone frames
  gateway -> binary assistant frames

JSON-RPC session.event / voice.event
  -> transcript.partial, transcript.final, voice.state, voice.error, ...
```

Der Media-Token sollte kurzlebig, an User, Voice-Session und Richtung gebunden
sein. Der normale Gateway-Bearer-Token gehört nicht als Query-Parameter in die
Media-URL.

Alternativ kann der bestehende WebSocket später echte Text- und Binary-Frames
multiplexen. Das spart eine Verbindung, koppelt aber RPC-Transport,
Clientgenerator und Media-Framing stark aneinander. Für den ersten Ausbau ist
ein eigener Media-Endpunkt einfacher zu testen und zu betreiben.

## Vorgeschlagener öffentlicher Vertrag

Die Namen sind ein Entwurf; entscheidend sind die getrennten Konzepte.

### Control-Methoden

```text
voice.session.open(session_id, capabilities)
voice.session.close(voice_session_id)
voice.turn.start(voice_session_id, activation, input_format)
voice.turn.end_input(voice_turn_id)
voice.turn.interrupt(voice_turn_id, sequence?)
voice.playback.completed(voice_turn_id)
```

`voice.turn.start` startet noch keinen Conversation-Turn mit einem leeren oder
künstlichen Text. Es öffnet einen Voice-Turn und dessen STT-Stream. Erst die
finale, normalisierte Transkription erzeugt serverseitig den User-Message- und
Conversation-Turn.

### Events

```text
voice.turn.started
voice.input.started
voice.transcript.partial
voice.transcript.final
voice.assistant.text.delta       # bestehendes Conversation-Event referenzieren
voice.assistant.audio.started
voice.assistant.audio.completed
voice.turn.completed
voice.turn.cancelled
voice.turn.failed
```

Jedes Event braucht mindestens:

- `voice_session_id`;
- `voice_turn_id`;
- nach der Transkription zusätzlich `conversation_turn_id`;
- monotone Sequenznummer;
- serverseitigen Zeitstempel.

Assistant-Text sollte nicht dupliziert gespeichert werden. Das Voice-Event darf
auf den Conversation-Turn verweisen; die bestehenden Conversation-Events
bleiben die Quelle für Text und Tool-Calls.

### Media-Frames

Ein Frame benötigt einen kleinen binären Header mit mindestens:

```text
version | kind | stream_id | sequence | timestamp | payload_length | payload
```

`kind` unterscheidet beispielsweise `input_pcm`, `output_pcm`, `end` und
`abort`. Audioformat und Codec werden einmal beim Öffnen ausgehandelt, nicht in
jedem Chunk wiederholt. Für den ersten Schritt reicht PCM S16LE mono. Später
kann Opus ergänzt werden, ohne das fachliche API zu verändern.

Für Mikrofonframes gilt eine begrenzte Queue. Ist der Client dauerhaft zu
langsam, wird der Stream mit einem expliziten Overrun-Fehler beendet; alte
Sprachaudioframes dürfen nicht stillschweigend minutenlang nachlaufen. Für
Assistant-Audio erzeugt der Gateway-TTS-Consumer durch seine begrenzte Queue
Backpressure bis zum Provider.

## Turn-Zustandsmodell

Voice-Turn und Conversation-Turn sind nicht identisch:

```text
OPEN
  -> LISTENING
  -> TRANSCRIBING
  -> WAITING_FOR_ASSISTANT   (ab hier existiert conversation_turn_id)
  -> SYNTHESIZING
  -> PLAYING
  -> COMPLETED

jeder aktive Zustand -> CANCELLED | FAILED
```

Diese Trennung löst das heutige Problem der Textschnittstelle. Eine
fehlgeschlagene oder leere Aufnahme muss keinen Conversation-Turn erzeugen. Ein
Text-Client startet weiterhin direkt einen Conversation-Turn. Ein Voice-Client
startet zuerst einen Voice-Turn, aus dem optional genau ein Conversation-Turn
entsteht.

`playback.completed` ist eine Bestätigung des aktiven Ausgabegeräts. Erst dann
kann das Gateway eine serverseitige Follow-up-Policy starten. Verliert der
Client die Verbindung, muss die Policy auslaufen oder die Voice-Session
abbrechen, statt eine Wiedergabe anzunehmen.

## Barge-in und niedrige Latenz

Barge-in wird geteilt:

- Der Client erkennt das lokale Signal (Wake Word oder Sprache trotz Echo
  Cancellation) und stoppt die Wiedergabe sofort.
- Parallel sendet er `voice.turn.interrupt` an das Gateway.
- Das Gateway bricht TTS und den zugehörigen Conversation-Turn ab bzw. steuert
  ihn nach der bestehenden Conversation-Semantik.
- Der Client sendet Pre-Roll ab der gemeldeten lokalen Sequenznummer in den
  neuen Input-Stream.

Das lokale Stoppen darf nicht auf die Netzwerkantwort warten. Der Gateway-
Abbruch bleibt trotzdem autoritativ für den fachlichen Zustand.

## Transkriptionen und Audio als Gateway-Ausgaben

Partielle Transkriptionen sind flüchtige Events. Die finale Transkription wird
als Text der User-Message persistiert und sollte strukturierte Herkunftsdaten
tragen, beispielsweise:

```json
{
  "modality": "voice",
  "voice_session_id": "...",
  "voice_turn_id": "...",
  "stt_provider": "deepgram",
  "audio_object_id": null
}
```

Rohaudio sollte standardmäßig **nicht** dauerhaft gespeichert werden. Falls
Recording aktiviert ist, schreibt der Media-Ingress Chunks in den vorhandenen
Object-Storage und die Conversation speichert nur eine Referenz samt Format,
Dauer und Aufbewahrungsrichtlinie. Das vermeidet große BLOBs in SQLite und
macht Datenschutz und Retention explizit.

Assistant-Audio ist zunächst ein flüchtiger Ausgabestream. Optional kann auch
dieser Stream objektbasiert archiviert und über eine Referenz an andere Clients
geliefert werden. Live-Wiedergabe darf nicht auf die Fertigstellung eines
vollständigen Audioobjekts warten.

## Mehrere Clients und Ownership

Conversation-Events dürfen weiterhin an mehrere Abonnenten gehen. Ein
Mikrofon-/Lautsprecherstream braucht jedoch einen eindeutigen Owner. Beim
Öffnen einer Voice-Session wird deshalb ein `device_id` registriert und für
jeden Voice-Turn ein Input- und Output-Owner bestimmt.

Andere Clients dürfen Transkriptionen und Status beobachten, aber nicht ohne
explizite Übergabe Audio einspeisen oder `playback.completed` bestätigen. Das
verhindert doppelte TTS-Wiedergabe, konkurrierende Mikrofone und versehentliche
Abbrüche durch einen nur beobachtenden Client.

## Konfiguration und Secrets

Nach der Migration liegen STT-/TTS-Provider, Modelle, Sprache, Timeouts und
Provider-Secrets in der Gateway-Konfiguration. Im Client verbleiben nur:

- Gateway-Adresse und Authentisierung;
- Gerätewahl und lokale Audioformate;
- Wake Word, VAD, Echo Cancellation und Barge-in-Einstellungen;
- lokale Ausgabe-, Observer- und Recording-Einstellungen.

Das ist ein wesentlicher Gewinn des Umbaus: neue Voice-Clients benötigen keine
Provider-SDKs und keine Provider-Zugangsdaten.

## Migrationsplan

### Phase 1: Vertrag und serverseitiges TTS

- `gateway.features.voice` mit Control-Modellen und Events anlegen.
- TTS-Port und Deepgram-Adapter ins Gateway verschieben.
- Assistant-Text serverseitig in TTS leiten und Audio über den neuen
  Media-WebSocket ausgeben.
- Der Client behält STT vorerst und sendet weiterhin Text an
  `turn.start`, empfängt Audio aber bereits vom Gateway.

Diese Zwischenphase reduziert TTS-/Providerlogik im Client und erprobt den
schwierigeren Downstream-Mediatransport, ohne den Inputpfad gleichzeitig
umzustellen.

### Phase 2: Audio-Ingress und serverseitiges STT

- Media-Upload, Formataushandlung, Sequenzierung und Backpressure ergänzen.
- STT-Port und Deepgram-Adapter ins Gateway verschieben.
- Partielle/finale Transkriptionen als Voice-Events veröffentlichen.
- Aus dem finalen Transkript serverseitig den Conversation-Turn starten.
- `CommandBridge` und `SpeechToTextBridge` aus dem Client entfernen.

Ab hier wird die Textschnittstelle nicht mehr vom Voice-Client als
Audio-Ersatz benutzt.

### Phase 3: serverseitige Voice-Orchestrierung

- Voice-Turn-Zustandsmaschine, Playback-Acknowledgement und Follow-up-Policy
  ins Gateway verschieben.
- Proaktive Conversation-Turns serverseitig einem aktiven Voice-Ausgabegerät
  zuordnen.
- `GatewayAgentSession`, große Teile der Handler und deren parallelen lokalen
  Voice-Zustand entfernen.
- Client-API auf `VoiceGatewaySession` plus `MediaTransport` reduzieren.

### Phase 4: optionale Aufzeichnung und weitere Clients

- Opt-in-Audioarchivierung über Object Storage ergänzen.
- Retention, Größenlimits und Berechtigungen definieren.
- Browser-/Mobile-Clients über denselben Voice-Control- und Media-Vertrag
  anbinden.
- Erst bei Bedarf Opus und Resume/Handover ergänzen.

## Was nicht 1:1 verschoben werden sollte

Der lokale `EventBus`, `VoiceChannel` und die Handler bilden heute gemeinsam
eine In-Process-Pipeline. Diese Klassen komplett ins Gateway zu kopieren würde
nur die bestehende Architektur an einen anderen Ort verschieben und parallel
zum bereits vorhandenen Conversation-Lebenszyklus einen zweiten Turn-Manager
erzeugen.

Stattdessen sollten die Provider-Ports und bewährten Streamingmechanismen
übernommen, die Zustandsführung aber als Gateway-Voice-Feature neu modelliert
werden. Insbesondere gilt:

- Gateway-IDs statt lokaler Integer-`turn_id`s;
- bestehende Conversation-Events statt eines zweiten Agent-Eventmodells;
- Gateway-DI statt Konstruktion aller Komponenten in `VoiceChannel`;
- öffentliche RPC-/Media-Verträge statt In-Process-Requests;
- persistierbare fachliche Zustände statt nur laufender Tasks.

## Definition of Done für den schlanken Client

Der Umbau ist erreicht, wenn der Client:

- keine STT-/TTS-Providerabhängigkeit und keine Provider-Secrets mehr besitzt;
- keinen `AgentSession`-Port und kein Mapping von Gateway- auf lokale
  Agent-Events mehr benötigt;
- keinen Conversation-Turn aus einem lokal erzeugten Text startet;
- nur Aktivierung, PCM-Upload, PCM-Playback, lokale Akustik und lokale Geräte
  orchestriert;
- nach einem Reconnect den autoritativen Voice-/Conversation-Zustand vom
  Gateway beziehen kann;
- durch einen Mock-Media-Gateway vollständig ohne Deepgram und Agent getestet
  werden kann.

Damit bleibt der Client dort komplex, wo Echtzeit-Hardware zwangsläufig
komplex ist, und wird dort schlank, wo er heute Gateway-Verantwortung lokal
nachbildet.
