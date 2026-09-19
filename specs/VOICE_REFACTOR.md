# Voice-Package-Refactoring

## Status und Leitidee

Dieser Entwurf beschreibt eine mögliche Neuordnung von `clients/voice`. Er ist
noch keine Implementierung.

Die beiden guten äußeren Bausteine bleiben erhalten:

```python
session = await VoiceSessionFactory.from_yaml()

async with session:
    await session.run()
```

Auch `voice.yml` bleibt der Composition Root für die konkrete Anwendung. Das
Refactoring soll an dieser Bedienung und am bestehenden Konfigurationsschema
zunächst nichts ändern.

Die zentrale Änderung ist: Der Datenfluss wird nicht mehr durch einen zentralen,
sessionweiten `EventBus` verdrahtet. Eine `VoiceSession` besitzt stattdessen
einen expliziten Runtime-Orchestrator. Befehle laufen als direkte
Methodenaufrufe, Audiodaten als
Streams und rein beobachtende Lifecycle-Meldungen über einen schmalen
Observer-Port. Der Gateway ist nur noch ein Adapter hinter einem eigenen
Voice-Backend-Port.

## Probleme im aktuellen Aufbau

Der aktuelle `EventBus` ist nicht nur ein Event-Mechanismus. Er erfüllt mehrere
unterschiedliche Aufgaben zugleich:

- Commands mit genau einem Empfänger, etwa `VoiceTurnRequested` und
  `AudioPlaybackRequested`
- Broadcasts für fachliche Zustandswechsel
- Transport von hochfrequenten Audiodaten über `UserAudioChunk` und
  `AssistantAudioChunk`
- implizite Steuerung von Startup und Cleanup über `SessionStarted`,
  `SessionEnded` und `VoiceResourcesClosing`
- Anbindung optionaler Integrationen, Logging und Tracing

Damit ist aus einem Aufruf nicht erkennbar, wer ihn verarbeitet, ob er Zustand
ändert und welche Fehler zurückkommen können. Der tatsächliche Ablauf verteilt
sich über die Subscriber in `VoiceChannel`, `GatewayVoiceBridge`, `AudioBridge`,
`ActivationCoordinator`, Barge-in und den Integrationen.

Hinzu kommen weitere Kopplungen:

- `VoiceChannel` kennt mit `GatewayVoiceSession` und `GatewayVoiceBridge`
  konkrete Gateway-Typen.
- `GatewayVoiceBridge` ist gleichzeitig Protokollübersetzer, Turn-State-Machine,
  Mikrofon-Uploader, Event-Publisher und Barge-in-Koordinator.
- Typen aus `gateway_rest_client` und `gateway_rpc_client` gelangen bis in die
  Ablaufsteuerung und deren Tests.
- Mehrere Komponenten leiten eigenen Zustand aus Bus-Events ab. Beispielsweise
  führen `ActivationCoordinator`, `GatewayVoiceBridge` und `VoiceChannel`
  teilweise parallele Vorstellungen darüber, ob gerade ein Turn aktiv ist und
  ob der Assistant antwortet.
- Ressourcen werden an mehreren Stellen geschlossen. Der Channel schließt die
  Gateway-Session, obwohl die Factory sie zugleich in einem `AsyncExitStack`
  registriert hat. Idempotenz verdeckt hier unklare Ownership.
- Tests müssen konkrete Klassen monkeypatchen oder Gateway-Klassen casten, statt
  kleine fachliche Ports zu faken.

Das Problem ist daher nicht der EventBus als Implementierung im Detail, sondern
dass er die Architektur und die Kontrollflüsse ersetzt.

## Ziele

1. Ein lesbarer, gerichteter Datenfluss mit genau einem Besitzer des
   Session- und Turn-Zustands.
2. Keine Abhängigkeit des Voice-Kerns von REST-, RPC- oder generierten
   Gateway-Typen.
3. Tests des kompletten Voice-Ablaufs mit In-Memory-Fakes, ohne Netzwerk,
   Gateway-Clients oder Bus-Wiring.
4. Eindeutige Ownership für Tasks und Ressourcen sowie deterministisches
   Shutdown-Verhalten.
5. Factory, `VoiceSession` und YAML-Konfiguration bleiben die stabile öffentliche
   API.
6. Die vorhandenen Fähigkeiten bleiben erhalten: Wake Word, externe
   Aktivierung, Pre-Roll, Barge-in, Echo-Unterdrückung, proaktive Turns,
   Snapshot-Restore, Follow-up-Konversationen, Earcons, Hue und Sonos.

## Nicht-Ziele

- Kein Umbau des Gateway-Protokolls oder seiner generierten Clients.
- Keine Änderung der Zuständigkeit: STT, Agent, TTS und persistierter Turn-State
  bleiben im Gateway.
- Keine neue allgemeine Dependency-Injection-Library.
- Keine Event-Sourcing-Infrastruktur im Voice-Client.
- Keine gleichzeitige Änderung des YAML-Schemas. Neue Backend-Typen können später
  ergänzt werden, wenn tatsächlich ein zweites Backend existiert.

## Architekturregeln

Die Kommunikation wird nach ihrer Semantik getrennt:

| Art | Mechanismus | Beispiele |
| --- | --- | --- |
| Command/Request | direkter, awaitbarer Methodenaufruf | Turn starten, unterbrechen, Playback bestätigen |
| kontinuierliche Daten | `AsyncIterator` oder dedizierter Reader/Writer | Mikrofon-PCM, Assistant-PCM |
| interner Kontrollimpuls | private Queue mit genau einem Consumer | Aktivierung, Backend-Lifecycle, Barge-in |
| reine Beobachtung | `VoiceLifecycleObserver`/Integrations-Fan-out | Logging, Hue, Sonos, Earcons |

Wichtig: Die private Kontroll-Queue ist kein neuer EventBus. Sie besitzt keine
Subscription-API, hat exakt einen Consumer und ist ein Implementierungsdetail der
Runtime. Observer dürfen weder den Zustand steuern noch Requests beantworten.

Alle austauschbaren Ports werden als abstrakte Basisklassen (`ABC`) modelliert,
nicht als `Protocol`. Implementierungen und Test-Fakes erben damit explizit von
ihrem Port; fehlende Methoden fallen bereits beim Instanziieren auf.

## Vorgeschlagenes Zielbild

```text
voice.yml
   |
   v
VoiceSessionFactory ---- baut/öffnet ----> Audio-Geräte, Integrationen,
   |                                       VoiceBackend-Adapter
   v
VoiceSession ------------- besitzt ------> VoiceRuntime + AsyncExitStack
                                              |
                         +--------------------+--------------------+
                         |                    |                    |
                  ActivationSource      VoiceBackend         BargeInStrategy
                         |                    |                    |
                         +------ control ----> VoiceRuntime <------+
                                              |
                               explizite Zustandsübergänge
                                              |
                      +-----------------------+--------------------+
                      |                                            |
             TurnInputUploader                           PlaybackController
                      |                                            |
          BufferedAudioInput -> VoiceBackend       VoiceBackend -> AudioOutput
                                              |
                                      LifecycleObservers
```

Die Runtime ist der einzige Besitzer des aktiven Turns. Sie entscheidet, ob
eine Aktivierung angenommen wird, wann Input startet oder endet, ob ein
Barge-in zulässig ist und wann ein Turn lokal abgeschlossen ist.

## 1. Gateway hinter einem Voice-Backend-Port

Der Kern soll nicht wissen, dass die konkrete Verbindung aus REST, JSON-RPC und
einem Media-Stream besteht. Er benötigt nur die fachlichen Fähigkeiten einer
entfernten Voice-Session.

Ein möglicher Port, bewusst auf Voice-Begriffe statt Gateway-Clientmodelle
zugeschnitten:

```python
class VoiceBackend(ABC):
    @property
    @abstractmethod
    def input_format(self) -> AudioFormat: ...

    @property
    @abstractmethod
    def output_format(self) -> AudioFormat: ...

    @property
    @abstractmethod
    def initial_state(self) -> BackendSessionState: ...

    @abstractmethod
    def events(self) -> AsyncIterator[BackendEvent]: ...

    @abstractmethod
    def output_audio(self) -> AsyncIterator[BackendAudioFrame]: ...

    @abstractmethod
    async def start_turn(self, request: StartTurn) -> StartedTurn: ...

    @abstractmethod
    async def send_input(self, turn: TurnRef, frame: AudioFrame) -> None: ...

    @abstractmethod
    async def end_input(self, turn: TurnRef, next_sequence: int) -> None: ...

    @abstractmethod
    async def interrupt(self, turn: TurnRef, sequence: int | None) -> None: ...

    @abstractmethod
    async def playback_completed(self, turn: TurnRef) -> None: ...
```

`TurnRef`, `StartTurn`, `StartedTurn`, `BackendEvent`, `BackendAudioFrame` und
`BackendSessionState` sind kleine Voice-eigene Datenmodelle. Insbesondere bleibt
der transportinterne `turn_index` im Gateway-Adapter und wird nicht Teil des
Core-Ports.

Die Verbindungserstellung ist ein zweiter Port, damit auch die Factory testbar
bleibt:

```python
class VoiceBackendConnector(ABC):
    @abstractmethod
    async def connect(self, options: BackendConnectionOptions) -> VoiceBackend: ...
```

Die Standardimplementierung `GatewayVoiceBackendConnector` erzeugt den
Gateway-Adapter. Nur unter `voice/adapters/gateway/` dürfen
`gateway_rest_client`, `gateway_rpc_client`, `httpx2`, Media-Framing und deren
Modelle importiert werden.

### Verantwortung des Gateway-Adapters

Der Adapter übernimmt vollständig:

- Öffnen/Schließen per REST
- Aufräumen bereits offener Voice-Sessions für den Raum
- RPC-Subscription und Resubscription nach Conversation-Ende
- Laden und Aktualisieren des Snapshots
- Sequence-Watermark und Deduplizierung
- Mapping von Gateway-Aktivierungen, Status und Events auf Voice-Domainmodelle
- Zuordnung von `turn_id` zu Media-`turn_index`
- Normalisierung der zwei eingehenden Verbindungen (Lifecycle und Media)
- Garantie, dass vor dem ersten PCM-Chunk logisch ein Audio-Start sichtbar ist
- sauberes Beenden beider Streams bei Close oder Verbindungsfehlern

Damit werden die heute wertvollen Details aus `GatewayVoiceSession` nicht
verworfen, sondern an der Adaptergrenze konzentriert.

### Keine verfrühte generische Abstraktion

Der Port soll exakt die aktuell benötigte Voice-Semantik ausdrücken. Er soll
nicht REST, RPC oder beliebige Provider generisch nachbauen. Ein Fake und der
Gateway-Adapter sind zunächst die einzigen Implementierungen. Erst ein echtes
zweites Backend rechtfertigt zusätzliche Konfigurationsvarianten.

## 2. Explizite Runtime statt zentralem EventBus

`VoiceChannel` und `GatewayVoiceBridge` werden durch eine intern verwendete
`VoiceRuntime` ersetzt. Sie besitzt:

- `VoiceBackend`
- `BufferedAudioInput`
- `PlaybackController`
- `ActivationSource`-Instanzen
- eine fertig gebundene `BargeInStrategy`
- `VoiceLifecycleObservers`
- exakt einen `TurnState`
- alle laufenden Tasks in einer strukturierten Task-Gruppe

Kontrollquellen schreiben typisierte interne Signale in eine private Queue:

```python
type RuntimeSignal = (
    ActivationReceived
    | BackendEventReceived
    | BargeInDetected
    | InputUploadFailed
    | PlaybackFinished
    | StopRequested
)
```

Nur `_run_control_loop()` liest diese Queue und verändert `TurnState`. Der
komplette Kontrollfluss ist dadurch in einem `match` auffindbar und lässt sich
sequenziell testen. PCM-Daten laufen nicht durch diese Queue, sondern über
dedizierte Streaming-Komponenten.

### Turn-State

Ein einzelner diskriminierter Zustand ersetzt verteilte Booleans und optionale
IDs. Beispielsweise:

```text
Ready
  -> Capturing(turn)       lokale oder Gateway-Aktivierung
  -> WaitingForAssistant   finales Transkript / Input-Ende
  -> Playing(turn)         erste Assistant-Ausgabe
  -> Ready                 Turn beendet/fehlgeschlagen/verworfen

Playing
  -> Interrupting(turn)    gültiges Barge-in
  -> Capturing(new_turn)   Interrupt bestätigt, neuer Turn gestartet

* -> Closing -> Closed
```

Der genaue Backend-Status darf detaillierter sein, aber ungültige Übergänge
müssen explizit behandelt werden. Ein zweiter Turn während eines aktiven Turns
wird beispielsweise sichtbar geloggt und abgelehnt; er verschwindet nicht in
einem beliebigen Subscriber.

`assistant_responding` wird aus dem Zustand abgeleitet und nicht separat in
`VoiceChannel` gepflegt. Gleiches gilt für `active_turn_id`, Turn-Index,
Speech-Start und Playback-Status.

### Strukturierte Nebenläufigkeit

`VoiceRuntime.run()` startet seine langlebigen Pumps gemeinsam und wartet auf
deren Ergebnis:

- Activation-Pump(s)
- Backend-Event-Pump
- Backend-Audio-Pump
- Barge-in-Pump
- Control-Loop

Endet eine notwendige Quelle unerwartet, endet die Session mit einer klaren
Fehlerursache. Beim Shutdown werden alle Tasks gemeinsam gecancelt und geawaitet.
Pro Turn erzeugte Upload- und Playback-Tasks gehören der Runtime und senden ihr
Abschluss- oder Fehlersignal zurück. Es bleiben keine frei laufenden Tasks
zurück.

## 3. Audiodaten als Pipeline, nicht als Events

Der Audiofluss wird als eigene Data Plane sichtbar:

```text
Input:
AudioInput -> EchoCancellation -> BufferedAudioInput -> TurnInputUploader
                                                   -> VoiceBackend.send_input()

Output:
VoiceBackend.output_audio() -> PlaybackController -> AudioPlayer -> AudioOutput
                                      |
                                      +-> VoiceBackend.playback_completed()
```

`UserAudioProducer`, `UserAudioChunk`, die Chunk-Subscriber im
`SpeechBargeIn` und die Audio-Events im `AudioBridge` können entfallen.

Der bestehende `BufferedAudioInput` ist bereits eine gute Grundlage, weil er
mehrere unabhängige Reader und Pre-Roll unterstützt:

- Der Turn-Uploader erhält einen Reader ab Aktivierungssequenz inklusive
  Pre-Roll.
- Speech-Barge-in erhält einen eigenen Live-Reader.
- Wake-Word-Erkennung erhält ebenfalls ihren eigenen Reader.

So konkurrieren die Consumer nicht um dieselben Chunks und Audiodaten müssen
nicht als fachliche Events modelliert werden.

`PlaybackController` bietet direkte Operationen wie `play_response`,
`play_clip`, `interrupt` und `stop`. Earcons und andere Integrationen bekommen
einen schmalen `AudioPlayback`-Port direkt injiziert. Der Umweg über
`AudioPlaybackRequested` und einen Request-Handler entfällt.

## 4. Aktivierung und Barge-in

`ActivationSource.activations()` ist bereits ein sinnvoller Port und kann
bleiben. Der `ActivationCoordinator` muss jedoch keinen Buszustand spiegeln.
Die Runtime pumpt die Quellen und entscheidet anhand ihres eigenen Zustands, ob
eine Aktivierung angenommen wird.

Eine Wake-Word-Erkennung liefert neben der `ListenActivation` eine optionale
beobachtbare Detection für Integrationen. Das Starten des Turns bleibt trotzdem
ein direkter Runtime-Befehl; die Notification startet niemals selbst einen Turn.

`BargeInStrategy.set_context()` sollte entfallen. Nachträgliches Binden macht
ungültige Zwischenzustände möglich und versteckt Abhängigkeiten. Die Factory
erstellt stattdessen eine vollständig gebundene Strategie, zum Beispiel mit
einem `AudioFrameSource`, `AudioFormat` und `EchoPresence`. Die Strategie liefert
weiterhin `BargeInSignal` als Stream. Ob das Signal im aktuellen Zustand gültig
ist, entscheidet ausschließlich die Runtime.

## 5. Integrationen und Beobachtbarkeit

Integrationen brauchen weiterhin semantische Lifecycle-Informationen, sollen
aber nicht am Kontrollfluss teilnehmen. Dafür gibt es einen einseitigen Port:

```python
class VoiceLifecycleObserver(ABC):
    @abstractmethod
    async def on_lifecycle_event(self, event: VoiceLifecycleEvent) -> None: ...
```

Alternativ kann die bestehende callback-basierte `VoiceIntegration`-API bleiben
und durch einen `VoiceIntegrationNotifier` explizit aufgerufen werden. Wichtig
ist weniger die Form als die Einschränkung:

- keine dynamischen Subscriptions
- keine Request-Handler
- kein PCM
- keine Ableitung von Core-Zustand aus Observern
- kein Zugriff auf Gateway-Typen

Logging und Event-Trace werden ebenfalls Observer. Die Runtime ruft den
Notifier an den sichtbaren Übergängen auf. Dadurch ist am Übergang direkt
erkennbar, welche Beobachtung ausgelöst wird.

Fehlersemantik:

- Fehler in `prepare()` oder `on_session_starting()` brechen den Start ab, weil
  eine Integration dann nicht sicher initialisiert ist.
- Fehler in späteren rein beobachtenden Callbacks werden pro Integration
  geloggt und isoliert; sie dürfen weder Turn-State noch Cleanup verhindern.
- `on_session_stopped()` wird für jede erfolgreich gestartete Integration genau
  einmal versucht.

Falls eine Integration fachlich kritisch sein soll, braucht sie einen eigenen
expliziten Port im Kontrollfluss und ist dann bewusst kein Observer mehr.

## 6. Factory und Session bleiben der Composition Root

`VoiceSessionFactory.from_yaml()` ist der bequeme öffentliche Einstieg und gibt
direkt eine fertig erzeugte `VoiceSession` zurück. Da beim Erzeugen bereits
Netzwerkverbindungen und externe Ressourcen geöffnet werden, ist die Methode
asynchron:

```python
session = await VoiceSessionFactory.from_yaml()
```

Intern lädt sie die Konfiguration, erzeugt eine Factory-Instanz und delegiert an
deren `create()`-Methode. Der normale Aufrufer sieht diesen Zwischenschritt nicht:

```python
class VoiceSessionFactory:
    @classmethod
    async def from_yaml(
        cls,
        path: str | Path | None = None,
        **dependencies: object,
    ) -> VoiceSession:
        config = VoiceSessionConfig.from_yaml(path)
        factory = cls(config, **dependencies)
        return await factory.create()
```

Die Instanzmethode `create()` bleibt für Tests, programmgesteuerte Konfiguration
und gezielte Dependency-Injection verfügbar. Die Aufgabe der Factory bleibt
eng: Konfiguration validieren, Adapter auswählen, Ressourcen öffnen und die
Objekte zusammensetzen. Sie enthält keine Turn-Logik.

Für Testbarkeit können konkrete Erzeuger injiziert werden:

```python
factory = VoiceSessionFactory(
    config,
    backend_connector=fake_connector,
    audio_device_factory=fake_audio_devices,
    activation_sources=(manual_activation,),
    integrations=(recording_integration,),
)
session = await factory.create()
```

Die Defaultwerte verwenden Gateway, lokale Audio-Hardware, Wake Word und die
YAML-konfigurierten Integrationen. Es ist keine Container-API und kein
Service-Locator nötig; die wenigen infrastrukturellen Erzeuger sind benannte
Konstruktorparameter.

`VoiceSession` bleibt die öffentliche, einmal verwendbare Lifecycle-Fassade:

- `run()` delegiert an die Runtime.
- `close()` stoppt zuerst die Runtime und schließt danach den `AsyncExitStack`.
- Der Exit-Stack ist alleiniger Besitzer externer Ressourcen wie Backend,
  PortAudio-Session und Sonos-Client.
- Runtime-Komponenten schließen ihre eigenen Tasks/Reader, aber nicht zusätzlich
  die externen Adapter.
- Close ist idempotent; jede konkrete Ressource wird trotzdem nur von einem
  Besitzer geschlossen.

`VoiceChannel` muss keine zweite öffentliche Fassade neben `VoiceSession`
bleiben. Falls der Name intern keinen Mehrwert mehr hat, wird er vollständig
durch `VoiceRuntime` ersetzt, ohne Kompatibilitätsalias.

## Mögliche Paketstruktur

```text
voice/
  __init__.py                 # nur VoiceSessionFactory, VoiceSession und echte API
  factory.py                  # Composition Root
  session.py                  # öffentliche Lifecycle-Fassade
  runtime.py                  # interner Orchestrator und Control-Loop
  models.py                   # Voice-eigene Session-/Turn-Datenmodelle

  backend/
    __init__.py               # öffentlicher Port und Domainmodelle
    port.py
    models.py

  adapters/
    gateway/
      connector.py            # REST/RPC-Verbindungsaufbau
      backend.py              # VoiceBackend-Implementierung
      mapper.py               # Gateway-Modell -> Voice-Modell
      media.py
      framing.py

  activation/
  barge_in/
  audio/
    buffered_input.py
    input_uploader.py
    playback.py
  echo_cancellation/
  integrations/
    notifier.py
  config/
```

Die exakte Zahl der Dateien ist nicht das Ziel. Die relevante Grenze lautet:
Core-Code importiert nur Voice-eigene Ports und Modelle; Protokollcode importiert
nach innen, niemals umgekehrt.

## Konkreter Ablauf eines normalen Turns

1. `VoiceSession.run()` startet `VoiceRuntime`.
2. Die Runtime bereitet Integrationen vor, startet den gepufferten Audioeingang
   und die langlebigen Pumps.
3. Eine `ActivationSource` liefert `ListenActivation(sequence=...)`.
4. Der Control-Loop akzeptiert sie nur im Zustand `Ready` und ruft direkt
   `backend.start_turn(...)` auf.
5. Die Runtime setzt `Capturing(turn)` und startet einen `TurnInputUploader` mit
   einem eigenen Reader inklusive Pre-Roll.
6. Der Backend-Adapter sendet normalisierte Transcript-/Turn-Events. Die Runtime
   stoppt den Uploader am fachlich definierten Übergang und wechselt nach
   `WaitingForAssistant`.
7. Backend-PCM fließt über `PlaybackController` zum Ausgang. Beim ersten
   tatsächlich abgespielten Chunk wechselt die Runtime nach `Playing` und
   informiert Observer.
8. Nach vollständigem Device-Playback ruft die Runtime direkt
   `backend.playback_completed(turn)` auf.
9. Beim Backend-Turn-Ende beendet die Runtime alle turn-lokalen Tasks, wechselt
   nach `Ready` und informiert Observer.

## Ablauf bei Barge-in

1. Die vollständig gebundene Strategie liest ihren eigenen Mikrofonstream und
   liefert `BargeInSignal(sequence)`.
2. Der Control-Loop akzeptiert das Signal nur in einem Zustand, in dem der
   Assistant tatsächlich antwortet.
3. `PlaybackController.interrupt()` leert unmittelbar den lokalen Puffer.
4. Die Runtime ruft `backend.interrupt(active_turn, sequence)` auf.
5. Nach lokal eindeutigem Abschluss des alten Turns startet sie direkt einen
   neuen Turn mit Aktivierungsart `BARGE_IN` und derselben Sequenz für Pre-Roll.

Dieser Ablauf steht dann an einer Stelle. Er wird nicht mehr als Kette aus
`VoiceTurnInterrupted` -> Gateway-Subscriber -> `VoiceTurnEnded` -> Request auf
dem Bus zusammengesetzt.

## Fehler- und Shutdown-Verhalten

Folgende Regeln sollten Teil des Vertrags sein:

- Ein unerwartet beendeter Backend-Control- oder Media-Stream ist ein fataler
  Sessionfehler. Ein aktiver Turn wird lokal beendet und `run()` liefert die
  ursprüngliche Ursache zurück.
- Ein Fehler beim Mikrofon-Capture ist fatal, weil keine weitere Aktivierung oder
  Sprache möglich ist.
- Ein Fehler im Upload beendet den betroffenen Turn kontrolliert. Ob danach die
  Session weiterlaufen darf, wird explizit anhand der Backend-Antwort entschieden
  und nicht durch einen verlorenen Task.
- Cancellation wird nie in einen normalen Fehler umgewandelt.
- Shutdown-Reihenfolge: keine neuen Aktivierungen, aktiven Turn bestmöglich
  unterbrechen, turn-lokale Tasks stoppen, Playback stoppen, Pumps stoppen,
  Observer beenden, externe Ressourcen über den Exit-Stack schließen.
- Jeder Schritt ist idempotent und versucht nachfolgende Cleanup-Schritte auch
  dann, wenn ein vorheriger fehlschlägt. Mehrere Fehler werden nachvollziehbar
  gruppiert oder geloggt.

## Teststrategie

Es sollen nur Tests entstehen, die Verhalten und öffentliche Verträge schützen.
Die wichtigsten Test Doubles sind klein:

- `FakeVoiceBackend`: nimmt Commands auf und stellt kontrollierbare Event- und
  Audiostreams bereit.
- `FakeAudioInput`/`FakeAudioOutput`: liefern beziehungsweise sammeln PCM.
- `ManualActivationSource` und `ManualBargeInStrategy`.
- `RecordingLifecycleObserver`.
- `FakeVoiceBackendConnector` für einen Factory-Test.

Sinnvolle Tests:

1. normaler Turn vom Activation-Signal bis Playback-Acknowledgement
2. Aktivierung während eines aktiven Turns wird abgelehnt
3. Barge-in unterbricht ausschließlich während einer Assistant-Antwort und nutzt
   die richtige Pre-Roll-Sequenz
4. proaktiver Turn öffnet keinen Mikrofon-Uploader
5. Restore eines aktiven Turns aus `initial_state`
6. Backend- oder Capture-Streamfehler beendet die Session ohne hängende Tasks
7. `close()` stoppt Runtime und Ressourcen jeweils genau einmal
8. Gateway-Adapter-Mapping, Watermark, Resubscription und Turn-ID/Index-Zuordnung
   als fokussierte Adaptertests
9. `await VoiceSessionFactory.from_yaml()` lädt weiterhin `voice.yml` und gibt
   direkt eine lauffähige Session zurück
10. Die explizit konstruierte Factory baut mit injiziertem Connector eine
    lauffähige Session

Tests des Core dürfen weder `gateway_rpc_client` noch `gateway_rest_client`
importieren. Tests des Gateway-Adapters dürfen deren Modelle gezielt verwenden.

## Schrittweise Migration

### Phase 1: Voice-Domain und Backend-Port

- Voice-eigene Backendmodelle und `VoiceBackend` definieren.
- Bestehende Gateway-Verbindung in einen Adapter verschieben und das Mapping
  dort kapseln.
- Snapshot-Restore, Watermark und Resubscription mit Adaptertests absichern.
- Factory über `VoiceBackendConnector` verbinden.

In dieser Phase darf der Adapter intern noch den bestehenden Bridge-Code nutzen,
aber der Core sieht bereits keine generierten Gateway-Typen mehr.

### Phase 2: Runtime und Turn-State

- `VoiceRuntime` mit privatem Control-Loop und explizitem `TurnState` einführen.
- Activation und Backend-Lifecycle direkt anbinden.
- Start, End, Fehler, proaktive Turns und Restore aus dem Bus herauslösen.
- `GatewayVoiceBridge` anschließend vollständig entfernen.

### Phase 3: Audio-Data-Plane

- `TurnInputUploader` und `PlaybackController` einführen.
- Barge-in und Wake Word an eigene `BufferedAudioInput`-Reader binden.
- `UserAudioChunk`, Assistant-Chunk-Events, `UserAudioProducer`, `AudioBridge` und
  `AudioPlaybackRequested` entfernen.

### Phase 4: Observer und Integrationen

- Bestehende `VoiceIntegration`-Callbacks über einen direkten Notifier aufrufen.
- Logging und Trace als Observer anbinden.
- Alle verbleibenden Core-Events und den `EventBus` entfernen.

### Phase 5: Ownership bereinigen

- `VoiceSession` zum einzigen öffentlichen Lifecycle-Owner machen.
- Externe Ressourcen ausschließlich über den Factory-Exit-Stack schließen.
- `VoiceChannel` vollständig entfernen oder intern vollständig umbenennen.
- Exporte in `voice/__init__.py` auf die beabsichtigte öffentliche API begrenzen.

Die Migration sollte pro Phase kompilier- und testbar bleiben. Innerhalb einer
Phase werden Umbenennungen vollständig durchgeführt; es entstehen keine
dauerhaften Kompatibilitätsaliase.

## Akzeptanzkriterien

Das Refactoring ist abgeschlossen, wenn:

- es unter `clients/voice/src/voice` keinen `EventBus` mehr gibt;
- Core-Module keine Gateway-REST-/RPC-/generierten Typen importieren;
- alle Gateway-spezifischen Imports unter `voice/adapters/gateway/` liegen;
- PCM ausschließlich über Audioports, Reader und Writer fließt;
- genau eine Runtime den aktiven Turn-Zustand besitzt;
- `await VoiceSessionFactory.from_yaml()` mit dem bestehenden `voice.yml` direkt
  eine fertige `VoiceSession` liefert;
- `VoiceSession.run()`/`close()` ein eindeutiges, idempotentes Lifecycle besitzen;
- Core-Ablauftests ausschließlich mit Voice-eigenen Fakes funktionieren;
- keine Tests konkrete Runtime-Klassen monkeypatchen oder Gateway-Typen in den
  Core casten müssen;
- Shutdown-, Streamfehler-, Restore-, proaktive Turn- und Barge-in-Pfade
  nachweislich keine Tasks oder Ressourcen zurücklassen.

## Empfehlung

Der wichtigste erste Schnitt ist nicht eine neue Ordnerstruktur, sondern der
`VoiceBackend`-Port zusammen mit einem einzigen Runtime-Zustand. Sobald Commands
direkt und Gateway-Events als Voice-eigene Modelle ankommen, kann der EventBus
schrittweise schrumpfen. Audio sollte als Nächstes herausgelöst werden, weil
Chunk-Streaming über einen Broadcast-Bus den Datenfluss besonders stark
verschleiert. Factory und Session können währenddessen außen stabil bleiben und
am Ende deutlich weniger Verantwortung tragen.
