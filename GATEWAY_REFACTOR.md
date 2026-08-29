# Gateway-Refactor: Diskussionsentwurf

> Status: Architekturvorschlag, noch keine Implementierung.
>
> Ziel dieses Dokuments ist eine gemeinsame Entscheidung über Domänengrenzen,
> RPC-Oberfläche und Migrationsreihenfolge. `pyrpckit` und die bidirektionale
> WebSocket-Verbindung bleiben grundsätzlich erhalten.

## 1. Ausgangslage und Ziel

Der Gateway funktioniert technisch bereits in zwei Richtungen:

- Clients schicken RPC-Requests über eine langlebige WebSocket-Verbindung.
- Der Server beantwortet Requests und schickt zusätzlich asynchrone
  `session.event`-Notifications über dieselbe Verbindung.
- `pyrpckit` beschreibt Methoden, Fehler und Notifications und erzeugt daraus
  Schema und Client.

Das eigentliche Problem ist daher nicht Full Duplex. Das Problem ist, dass die
aktuelle Quellstruktur fachliche Grenzen, Application Use Cases und
Connection-/Transportmechanik nicht klar voneinander trennt.

Das Zielbild soll folgende Eigenschaften haben:

1. Persistierte fachliche Konzepte werden als echte Domainmodelle abgebildet.
2. Fachliche Regeln sind ohne Datenbank, Scheduler, Pydantic, Dishka,
   WebSocket oder `pyrpckit` testbar.
3. RPC ist ein dünner bidirektionaler Adapter und bestimmt nicht die
   Domänengrenzen.
4. Infrastructure implementiert Ports und übersetzt zwischen Domain und
   technischen Repräsentationen.
5. Eine neue Automation-Art oder ein neuer Conversation Use Case soll lokal
   ergänzt werden können, ohne zentrale Gateway-Dateien an vielen Stellen zu
   ändern.

Wichtig: Nicht alles Persistierte ist automatisch Domainlogik, und nicht alles
Flüchtige ist automatisch Presentation. Ein persistierter Datensatz kann ein
rein technischer Checkpoint sein. Entscheidend ist, ob Zustand und Regeln eine
fachliche Bedeutung haben. Für Cara sind Session, Conversation-Einträge und
Automation fachlich. Eine nur für die Lebenszeit eines Sockets bestehende
Subscription ist dagegen zunächst Connection-Zustand.

## 2. Was aus `fastapi-canon` übernommen werden soll

Referenz: [mathisarends/fastapi-canon](https://github.com/mathisarends/fastapi-canon),
insbesondere `guides/architecture.md`, `guides/domain.md` und der Tasks-Slice.

Übernommen werden die nach innen gerichteten Abhängigkeitsregeln:

```text
presentation  ──> application ──> domain
infrastructure ─────────────────> domain/application ports
composition root ───────────────> alle äußeren Layer
```

Konkret:

- Feature Ownership statt eines globalen Ordners je technischer Schicht.
- Normale Python-Klassen für Aggregate mit privatem Zustand und benannten
  Zustandsübergängen.
- Frozen Dataclasses nur für immutable Value Objects und Result Records.
- Frameworkfreie Domainmodelle und Domain Exceptions.
- Vom inneren Layer besessene Ports; konkrete Adapter implementieren diese
  explizit.
- Explizite Mappings an Storage- und Transportgrenzen.
- Application Services orchestrieren Use Cases, enthalten aber keine
  WebSocket-, SQL-, Scheduler- oder Pydantic-Typen.
- Ownership wird nicht im RPC-Handler entschieden. Sie ist Teil des
  fachlichen Ladens bzw. einer Domainregel.

Nicht übernommen wird die Annahme eines kurzlebigen HTTP Request/Response-
Zyklus. Beim Gateway ist die Presentation ein langlebiger Full-Duplex-Adapter.
Das verändert die Lebensdauer und den Output-Pfad, aber nicht die Richtung der
Abhängigkeiten.

## 3. Ist-Zustand

### 3.1 Conversation

Der Slice `gateway.features.conversation` enthält aktuell mehrere verschiedene
Dinge:

- das persistierte `Session`-Aggregate mit Messages und Tool Calls;
- Agent-Orchestrierung und Background Tasks in `ConversationService`;
- transienten Eventversand über `EventBroker`;
- Connection-Subscriptions;
- RPC-Handler für `session.*`, `turn.*` und `subscription.*`;
- Wire Events und deren Mapping.

Positiv ist, dass `Session` schon tatsächliches Domainverhalten besitzt. Zum
Beispiel verhindert das Aggregate neue Messages während einer offenen Tool-
Call-Sequenz und kontrolliert Auflösung und Fehlschlagen von Tool Calls.

Unklar sind dagegen diese Grenzen:

- `GatewayEvent` liegt in `domain/models.py`, ist aber mit `data`, `metadata`,
  `sequence` und `request_id` eher ein Application-/Streaming-Modell als ein
  Domainobjekt.
- `EventBroker` vereint Publishing, Connection Registry, Subscription Registry
  und Receiving in einem Interface.
- `SubscriptionRpcMethods` liegt im Conversation Feature, obwohl es den
  flüchtigen Zustand einer konkreten WebSocket-Verbindung verändert.
- `SessionRepository` persistiert das Aggregate und dient gleichzeitig als
  atomarer Turn-Lock (`claim_turn`/`release_turn`).
- `ConversationService` besitzt Session Use Cases, Agent Lifecycle, Turn
  Execution, Background-Task-Verwaltung, Retry-Verhalten und Eventprojektion.
- `turn.prepare` und `turn.finish` verändern keine Conversation Domain, sondern
  reichen Lifecycle-Hinweise an den Agent Runner weiter.

### 3.2 Automation

`automation/domain/models.py` enthält derzeit:

- `AutomationEnvelope`;
- `SessionAutomationTarget`;
- `ReminderPayload`.

Diese Typen beschreiben vor allem das serialisierte Scheduler-Payload. Eine
Automation als fachliche Entität mit Identität, Zeitplan, Ziel, Aktion und
benannten Zustandsübergängen existiert nicht. Deshalb leakt das technische
Scheduler-Modell durch alle Layer:

```text
RPC schema
  -> AutomationService
  -> scheduler.Trigger / ScheduledJob
  -> AutomationEnvelope
  -> Scheduler SQLite store
```

Konkrete Folgen:

- `AutomationService` hängt direkt von `Scheduler[AutomationEnvelope]` ab.
- Application und Presentation arbeiten mit `ScheduledJob` und `Trigger` aus
  der Scheduler Library.
- `list_for_session` lädt alle Jobs und filtert im Speicher.
- Die Regel „diese Automation gehört zu dieser Session“ ist ein Filter bzw.
  Vergleich im Application Service, nicht Verhalten eines Domainobjekts.
- Beim Erstellen wird nicht geprüft, ob die Session existiert.
- Der Scheduler Store ist gleichzeitig Persistence Model, Repository und
  Ausführungsmechanismus.
- `gateway.infrastructure.scheduler` kennt sowohl Automation als auch
  Conversation und koppelt damit zwei Features in einem globalen Adapter.
- Der Payloadname `Envelope` und `schema_version` sind Storage-/Codec-Sprache,
  keine gute fachliche API der Automation.

### 3.3 RPC und Feature-Komposition

Die öffentliche Methode und die interne Modulstruktur spiegeln sich aktuell
fast eins zu eins:

```text
session.*       -> SessionRpcMethods
turn.*          -> TurnRpcMethods
subscription.*  -> SubscriptionRpcMethods
automation.*    -> AutomationRpcMethods
```

Das ist mechanisch übersichtlich, suggeriert aber Domänen, die es so nicht
gibt. `subscription` ist keine gleichwertige fachliche Domäne neben Session und
Automation. Umgekehrt kann eine fachliche Domäne mehrere RPC-Ressourcen und
mehrere ausgehende Notification-Typen besitzen.

Zusätzlich baut `GatewayProvider` alle konkreten Handler manuell. Damit müssen
beim Ergänzen einer RPC-Capability aktuell Feature-Definition, Provider,
Protokoll und Connection-Komposition synchron angepasst werden.

## 4. Vorgeschlagene fachliche Grenzen

### 4.1 Bounded Context `conversation`

Conversation besitzt:

- das `Session`-Aggregate;
- Conversation Entries (`UserMessage`, `AssistantMessage`, Tool-Call-Sequenz);
- Regeln über zulässige Zustandsübergänge innerhalb einer Session;
- die fachliche Kanalreferenz einer Session;
- Repository-Ports für Session-Persistenz.

Ein Turn muss nicht automatisch ein eigenes Aggregate sein. Derzeit hat ein
Turn keine persistierte Identität und keinen eigenständigen Lifecycle im
Domainmodell. Er ist vor allem ein Application Use Case, der eine Session und
einen Agent Runner koordiniert. Falls Turns später persistiert, wiederaufnehmbar
oder separat abfragbar werden, kann daraus bewusst eine `Turn`-Entität oder ein
eigenes Aggregate entstehen.

`turn_active` ist ein Grenzfall. Die Regel „höchstens ein aktiver Turn pro
Session“ ist fachlich relevant, ihre atomare Durchsetzung ist aber technische
Concurrency-Koordination. Daher sollte sie über einen eigenen Port wie
`TurnLease` oder `TurnCoordinator` ausgedrückt und vom SQL-Adapter atomar
implementiert werden, statt Teil des allgemeinen `SessionRepository` zu sein.

### 4.2 Bounded Context `automation`

Automation besitzt ein echtes persistiertes Aggregate. Ein möglicher erster
Schnitt:

```python
class Automation(Aggregate):
    def __init__(
        self,
        owner: AutomationOwner,
        target: AutomationTarget,
        schedule: Schedule,
        action: AutomationAction,
        name: str | None = None,
        *,
        id: str | None = None,
        created_at: datetime | None = None,
    ) -> None:
        ...

    @classmethod
    def create_for_session(
        cls,
        *,
        session: SessionRef,
        schedule: Schedule,
        action: AutomationAction,
        name: str | None = None,
    ) -> Self:
        ...

    def require_session(self, session_id: UUID) -> None:
        if self._target.session_id != session_id:
            raise AutomationNotFound(self.id)

    def reschedule(self, schedule: Schedule) -> Self:
        self._schedule = schedule
        return self

    def change_action(self, action: AutomationAction) -> Self:
        self._action = action
        return self
```

Der genaue Name der Ownership-Methode ist offen. Entscheidend ist: Die Regel
wird an einem Domainobjekt oder in einer reinen Domain Policy getestet, nicht
implizit durch ein Scheduler-Filter implementiert.

Die Automation sollte mindestens diese Konzepte voneinander trennen:

- **Owner**: In wessen fachlichem Namensraum liegt die Automation?
- **Target**: Wo wird sie bei Fälligkeit ausgeführt?
- **Schedule**: Wann wird sie fällig?
- **Action**: Was soll bei Fälligkeit passieren?
- **Execution state**: aktiv, pausiert, letzte/nächste Ausführung, falls diese
  Angaben fachlich gebraucht werden.
- **Origin/Audit**: Aus welchem Turn wurde sie angelegt? Das ist nicht zwingend
  Teil der ausführbaren Action.

`ReminderPayload` vermischt heute Action und Audit (`instruction` plus
`created_from_turn_id`). Ein besseres Modell könnte beispielsweise aus
`PromptAction(instruction)` und `AutomationOrigin(created_from_turn_id)`
bestehen.

### 4.3 Connection und Event Stream

Die WebSocket-Verbindung ist kein Bounded Context, sondern der bidirektionale
Presentation Adapter.

Sie besitzt:

- Authentifizierung und Connection-ID;
- den `pyrpckit.RpcServer` für eingehende Requests;
- Serialisierung von Responses und Notifications;
- einen Send Lock;
- flüchtige Subscriptions dieser konkreten Verbindung;
- Start und Ende des Event-Forwarding-Tasks.

Solange Subscriptions nur bis zum Disconnect leben und nicht persistiert
werden, gehören sie nicht in die Domain. Ihre Autorisierungsentscheidung kann
trotzdem einen Application Use Case aufrufen. Wenn Subscriptions später
persistiert, zwischen Geräten synchronisiert oder als Produktfunktion verwaltet
werden, werden sie zu einem eigenen fachlichen Modell.

Für den Eventpfad ist eine Trennung sinnvoll:

```text
Domain transition
  -> Application Event / Output Port
  -> Event distribution adapter
  -> connection subscription registry
  -> pyrpckit notification
  -> WebSocket
```

`ChatDelta` ist beispielsweise kein persistiertes Domain Event, sondern ein
flüchtiges Agent-/Application-Output. `ToolCallCompleted` kann zugleich einen
persistierten Domainzustand verändern und ein Streaming Event auslösen. Diese
beiden Rollen sollten nicht durch einen einzigen untypisierten `GatewayEvent`
verschmolzen werden.

## 5. Vorgeschlagene Layer und Ordnerstruktur

Der Slice bleibt vertikal nach fachlichem Feature organisiert; Full-Duplex-
Mechanik sitzt als äußerer Adapter daneben.

```text
gateway/
├── features/
│   ├── conversation/
│   │   ├── domain/
│   │   │   ├── session.py
│   │   │   ├── entries.py
│   │   │   ├── values.py
│   │   │   ├── repositories.py
│   │   │   └── exceptions.py
│   │   ├── application/
│   │   │   ├── session_service.py
│   │   │   ├── turn_service.py
│   │   │   ├── turn_execution.py
│   │   │   ├── events.py
│   │   │   └── ports.py
│   │   ├── infrastructure/
│   │   │   ├── persistence.py
│   │   │   ├── turn_lease.py
│   │   │   ├── agent_adapter.py
│   │   │   └── provider.py
│   │   ├── presentation/
│   │   │   └── rpc/
│   │   │       ├── handler.py
│   │   │       ├── schemas.py
│   │   │       ├── mapping.py
│   │   │       └── protocol.py
│   │   └── feature.py
│   └── automation/
│       ├── domain/
│       │   ├── automation.py
│       │   ├── schedule.py
│       │   ├── action.py
│       │   ├── repository.py
│       │   └── exceptions.py
│       ├── application/
│       │   ├── service.py
│       │   ├── execution.py
│       │   └── ports.py
│       ├── infrastructure/
│       │   ├── scheduler_repository.py
│       │   ├── codec.py
│       │   ├── runner.py
│       │   └── provider.py
│       ├── presentation/
│       │   └── rpc/
│       │       ├── handler.py
│       │       ├── schemas.py
│       │       ├── mapping.py
│       │       └── protocol.py
│       └── feature.py
├── presentation/
│   └── websocket/
│       ├── connection.py
│       ├── subscriptions.py
│       ├── event_forwarder.py
│       ├── provider.py
│       └── router.py
└── infrastructure/
    └── database/
```

Diese Baumstruktur ist kein Zwang zu vielen Ein-Datei-Klassen. Kleine Module
dürfen zusammenbleiben. Maßgeblich ist, dass eine Datei genau eine erkennbare
Verantwortung und eine klare Abhängigkeitsrichtung hat.

## 6. Automation im Detail

### 6.1 Domain Value Objects

Der Zeitplan ist fachlicher Zustand und sollte nicht als `scheduler.Trigger`
im Application Layer erscheinen:

```python
@dataclass(frozen=True, slots=True)
class AtSchedule:
    run_at: datetime


@dataclass(frozen=True, slots=True)
class IntervalSchedule:
    every: timedelta
    run_immediately: bool = False


@dataclass(frozen=True, slots=True)
class CronSchedule:
    expression: str
    timezone: str


type Schedule = AtSchedule | IntervalSchedule | CronSchedule
```

Die Domain entscheidet über fachliche Invarianten wie ein positives Intervall
oder erlaubte Zustandsübergänge. Presentation validiert die Wire Form. Der
Scheduler Adapter übersetzt `Schedule` in `At`, `Interval` oder `Cron`.

Auch Targets und Actions sind Domain Values, nicht Wire Schemas:

```python
@dataclass(frozen=True, slots=True)
class SessionTarget:
    session_id: UUID


@dataclass(frozen=True, slots=True)
class PromptAction:
    instruction: str
```

### 6.2 Ownership als explizite Domainregel

Hier muss zuerst die fachliche Bedeutung geklärt werden. Mindestens drei
Modelle sind denkbar:

1. **Session-owned und Session-targeted**: Eine Automation gehört exakt einer
   Session und läuft immer dort. Das entspricht dem aktuellen Verhalten.
2. **Channel-owned, Session-targeted**: Eine Automation gehört langfristig zu
   einem Channel, wurde aber aus einer konkreten Session angelegt.
3. **Channel-owned und Channel-targeted**: Bei Fälligkeit wird die aktuelle
   Session des Channels geöffnet und dort ausgeführt. Das überlebt Session-
   Wechsel fachlich sauberer.

Owner und Target sollten nicht vorschnell identisch modelliert werden. Genau
hier steckt die von außen sichtbare Regel „gehört zu diesem Channel/dieser
Session oder nicht“.

Unabhängig von der Wahl sollten Tests ungefähr so aussehen:

```python
def test_automation_rejects_a_different_session() -> None:
    automation = automation_for(session_id=SESSION_A)

    with pytest.raises(AutomationNotFound):
        automation.require_session(SESSION_B)


def test_reschedule_preserves_ownership_and_identity() -> None:
    automation = automation_for(session_id=SESSION_A)

    automation.reschedule(NEW_SCHEDULE)

    assert automation.id == AUTOMATION_ID
    assert automation.target == SessionTarget(SESSION_A)
    assert automation.schedule == NEW_SCHEDULE
```

Eine Alternative ist eine reine Domain Policy
`AutomationAccess.require_owner(automation, owner)`. Das ist sinnvoll, wenn
die Regel mehrere Aggregate oder Value Objects benötigt. Ein stateless Helper
ohne fachlichen Namen wäre dagegen nur verschobene Applicationlogik.

### 6.3 Repository-Port

Der Application Service soll kein Scheduler-Objekt sehen:

```python
class AutomationRepository(ABC):
    @abstractmethod
    async def get(self, automation_id: str) -> Automation | None: ...

    @abstractmethod
    async def list_for_owner(
        self,
        owner: AutomationOwner,
    ) -> tuple[Automation, ...]: ...

    @abstractmethod
    async def save(self, automation: Automation) -> Automation: ...

    @abstractmethod
    async def remove(self, automation: Automation) -> None: ...
```

Ob `get` bereits nach Owner scoped oder erst das geladene Aggregate seine
Ownership prüft, ist eine Sicherheitsentscheidung:

- Ein owner-scoped Query ist effizient und verhindert fremde Ressourcen schon
  im Storage Adapter.
- Eine explizite Domainprüfung ist direkt als Fachregel sichtbar und testbar.

Beides lässt sich kombinieren: `get_for_owner` ist der produktive Pfad, während
das Aggregate seine Invariante ebenfalls besitzt. In beiden Fällen wird nach
außen derselbe Not-found-Fehler verwendet, damit fremde IDs nicht aufgedeckt
werden.

### 6.4 Persistenzstrategie

Es gibt zwei realistische Varianten.

#### Variante A: Scheduler Store bleibt zunächst Source of Truth

`SchedulerAutomationRepository` implementiert `AutomationRepository` und mappt
zwischen `ScheduledJob` und `Automation`. Codec und `schema_version` bleiben
vollständig im Infrastructure Layer.

Vorteile:

- kleiner, risikoarmer Refactor;
- keine sofortige Migration der bestehenden Scheduler-Daten;
- Domain und Application werden trotzdem technisch entkoppelt.

Nachteile:

- Listen nach Owner können je nach Scheduler Store ineffizient bleiben;
- Scheduler-Persistenz und Automation-Persistenz bleiben eng gekoppelt;
- für mehrere Gateway-Instanzen ist die aktuelle SQLite-Lösung begrenzt.

#### Variante B: Gateway-Datenbank ist Source of Truth

Automation erhält eigene Tabellen und ein SQL Repository. Der Scheduler wird
nur Ausführungsadapter. Änderungen an Automation und Scheduling benötigen dann
eine zuverlässige Synchronisation, beispielsweise Outbox/Dispatcher oder einen
Scheduler, der fällige Automations direkt aus der Datenbank claimed.

Vorteile:

- fachliche Queries und Ownership können effizient im Repository ausgedrückt
  werden;
- sauberer Weg zu Pausieren, Historie, Status und Multi-Instance-Betrieb;
- Automation ist nicht durch das Datenmodell einer Library definiert.

Nachteile:

- deutlich größerer Schritt;
- Dual-Write zwischen Automation und Scheduler wäre ohne Outbox fehleranfällig;
- Migration und Claiming-Semantik müssen bewusst entworfen werden.

**Empfehlung für den ersten Refactor:** Variante A als Adapter einführen, aber
Domain und Port bereits so schneiden, dass Variante B später nur den Adapter
ersetzt. Kein Dual-Write als Zwischenlösung.

### 6.5 Ausführung über Featuregrenzen

Der Automation Scheduler soll nicht direkt `ConversationService` aus einem
globalen Infrastructure-Modul importieren. Automation besitzt stattdessen einen
caller-owned Output Port, zum Beispiel:

```python
class AutomationActionExecutor(ABC):
    @abstractmethod
    async def execute(
        self,
        automation: Automation,
        occurrence: AutomationOccurrence,
    ) -> None: ...
```

Ein äußerer Adapter übersetzt `SessionTarget + PromptAction` in den passenden
Conversation Use Case. Der Scheduler Runner lädt die Automation und ruft den
Executor. Dadurch kennt die Automation Application weder den konkreten
Scheduler noch `ConversationService`.

## 7. Conversation im Detail

### 7.1 Session bleibt Aggregate Root

Das bestehende `Session`-Modell ist eine gute Basis. Es soll weiterhin Regeln
wie diese kontrollieren:

- keine neue User-/Assistant-Message bei offenen Tool Calls;
- Tool Calls werden nur innerhalb einer gültigen Sequenz ergänzt;
- nur pending Tool Calls können abgeschlossen oder fehlgeschlagen werden;
- persistierte Entries bleiben geordnet.

`ChannelRef` ist ein passendes immutable Value Object. `GatewayEvent` und
`GatewayEventType` sollten dagegen aus der Domain heraus in den Application-
Eventpfad verschoben und möglichst typisiert werden.

### 7.2 Application Services nach Use-Case-Kohäsion

Die Trennung soll nicht die RPC-Prefixes kopieren. Eine mögliche Aufteilung ist:

- `SessionService`: create, open, get;
- `TurnService`: prepare, start, cancel und serverinitiierter Turn;
- `TurnExecution`: Agent Events verarbeiten, Domainzustand speichern und
  Application Events veröffentlichen;
- `TurnTaskRegistry`: laufende In-Process-Tasks verwalten;
- `TurnLease`: genau einen aktiven Turn pro Session koordinieren.

Das ist keine Behauptung, dass `turn` eine eigene Domäne ist. Es ist lediglich
ein kohärenter Application Workflow innerhalb von Conversation.

Der Automation Use Case sollte nicht als Sondermethode mit eigenem Retry-Loop
im allgemeinen `ConversationService` wachsen. Besser ist ein expliziter
serverinitiierter Startmodus:

```python
await turn_service.start(
    session_id=target.session_id,
    input=TurnInput.system(instruction),
    conflict_policy=TurnConflictPolicy.WAIT,
    metadata=...,
)
```

Interactive RPC könnte dieselbe Pipeline mit
`TurnConflictPolicy.REJECT` verwenden. Damit bleibt der Unterschied benannt,
ohne zwei weitgehend duplizierte Ausführungswege zu erzeugen.

### 7.3 Persistenz und Concurrency trennen

Vorgeschlagene Ports:

```python
class SessionRepository(ABC):
    async def find_by_id(self, session_id: UUID) -> Session | None: ...
    async def find_latest_by_channel(self, channel: ChannelRef) -> Session | None: ...
    async def save(self, session: Session) -> Session: ...


class TurnLease(ABC):
    async def acquire(self, session_id: UUID) -> bool: ...
    async def release(self, session_id: UUID) -> None: ...
```

Der SQL Adapter darf intern weiterhin dieselbe Tabelle verwenden. Der Port
zeigt aber, dass Aggregate-Persistenz und exklusives Claiming verschiedene
Verantwortungen sind.

Für `open_session` braucht die aktuelle globale `asyncio.Lock`-Lösung bei
mehreren Prozessen ohnehin eine DB-seitige Eindeutigkeit bzw. Transaktion.
Welche Definition von „aktuelle Session eines Channels“ gilt, sollte als
fachliche Regel dokumentiert und durch Storage Constraints unterstützt werden.

## 8. RPC-Oberfläche und Full Duplex

### 8.1 RPC-Namespace ist keine Domainarchitektur

Methodennamen sind ein öffentliches Protokolldesign. Ordner und Services sind
interne Architektur. Beide dürfen zusammenpassen, müssen aber nicht dieselben
Grenzen haben.

Für die RPC-Namen sind zwei Varianten sinnvoll:

#### Variante 1: Bestehende Resource Prefixes beibehalten

```text
session.create
session.open
session.get
turn.prepare
turn.start
turn.finish
turn.cancel
automation.list
automation.get
automation.create
automation.update
automation.delete
events.subscribe
events.unsubscribe
session.event              # Notification
```

Dabei wird nur `subscription.*` zu `events.*`, weil das die technische
Capability besser benennt. Die internen Handler können trotzdem je Feature
zusammengefasst sein.

Vorteil: resource-orientierter generierter Client und geringe Protokolländerung.

#### Variante 2: Fachlich unter Conversation gruppieren

```text
conversation.create
conversation.open
conversation.get
conversation.prepare
conversation.start
conversation.finish
conversation.cancel
conversation.subscribe
conversation.unsubscribe
conversation.event
automation.*
```

Vorteil: Im Client ist die zusammengehörige Conversation Capability sofort
sichtbar. Nachteil: Subscription wirkt dadurch stärker fachlich, obwohl sie
Connection-Zustand ist, und Methoden wie `conversation.start` sind etwas
weniger präzise.

**Vorläufige Empfehlung:** Variante 1, aber `subscription.*` in `events.*`
umbenennen und die interne Dateitrennung nicht länger aus den Prefixes ableiten.
Das öffentliche API bleibt gut lesbar, während die Architektur sauberer wird.
Da das Projekt vollständige Renames statt Compatibility Aliases bevorzugt,
sollte eine beschlossene Umbenennung Schema und generierten Client in einem
Schritt aktualisieren.

### 8.2 Dünne RPC-Handler

Ein Handler macht nur:

1. Wire Schema entgegennehmen;
2. in Domain/Application Values mappen;
3. einen Use Case aufrufen;
4. Resultat in Wire Response mappen.

Ownership, Scheduler-Auswahl, SQL, Retry-Policy und Connection Forwarding
gehören nicht in den Handler.

Es ist nicht nötig, je Prefix eine eigene Handlerklasse zu haben. Ein
`ConversationRpcHandler` kann Session- und Turn-Methoden enthalten, solange er
linear und klein bleibt. Connection-scoped Methoden wie subscribe/unsubscribe
können in einem `EventStreamRpcHandler` direkt beim WebSocket Adapter liegen.

### 8.3 Notifications als gleichwertiger Output

Full Duplex bedeutet, dass Presentation nicht nur Responses mappt. Sie mappt
auch Application Outputs in `RpcNotification`:

```text
incoming frame
  -> pyrpckit request validation
  -> RPC handler
  -> application use case
  -> domain / ports
  -> pyrpckit response

application output
  -> event distributor
  -> connection subscription
  -> notification mapper
  -> pyrpckit notification
  -> outgoing frame
```

Der gemeinsame `_send_lock` in `GatewayConnection` bleibt wichtig, weil
Responses und Notifications konkurrierend über denselben Socket laufen. Diese
Mechanik ist eine Stärke des aktuellen Designs und soll nicht in Domain oder
Application verschoben werden.

## 9. Feature-Komposition und Erweiterbarkeit

`Feature` sollte neben Protokolldefinition und Providern auch deklarieren
können, wie seine Handler für eine Connection erzeugt werden. Ziel ist, dass
`GatewayProvider` nicht jeden konkreten Feature-Handler importiert.

Eine mögliche Richtung:

```python
feature = RpcFeature(
    name="automation",
    protocol=AUTOMATION_PROTOCOL,
    providers=(AutomationProvider,),
    handler_types=(AutomationRpcHandler,),
)
```

Connection-spezifische Handler brauchen Context wie `client_id` und dürfen
deshalb weiterhin im WebSocket Adapter zusammengesetzt werden. Die Registry
soll deklarativ sein; sie darf aber nicht zu Service-Locator-Magie führen. Die
konkreten Konstruktorabhängigkeiten müssen typisiert und navigierbar bleiben.

Bevor diese Registry generalisiert wird, sollte geprüft werden, was Dishka für
`Scope.SESSION` und Handler Collections direkt leisten kann. Ein abstrahiertes
Plugin-System nur für vier Handler wäre verfrüht. Zuerst sollten die fachlichen
Grenzen stimmen.

## 10. Teststrategie

### 10.1 Domain Tests

Ohne Fixtures für DB, Scheduler oder WebSocket:

- Automation Ownership zu Session/Channel;
- Reschedule/Action Change erhält Identität und Owner;
- ungültige Schedule Values;
- erlaubte Statusübergänge einer Automation;
- bestehende Session-/Tool-Call-Invarianten.

### 10.2 Application Tests

Mit kleinen In-Memory-Fakes der Ports:

- Create/Get/Update/Delete Automation orchestriert Repository und Domain;
- fremder Owner erhält denselben Not-found-Fehler wie eine fehlende Automation;
- Automation Execution dispatcht Target und Action korrekt;
- interactive Turn rejected einen belegten Lease;
- scheduled Turn wartet entsprechend seiner Conflict Policy;
- Turn Execution persistiert Domainänderungen und veröffentlicht typisierte
  Outputs in korrekter Reihenfolge.

### 10.3 Adapter Contract Tests

- Scheduler Adapter mappt Domain `Schedule` verlustfrei auf Trigger und zurück;
- Codec versioniert nur die persistierte Repräsentation;
- SQL Repository rekonstruiert Aggregate vollständig;
- RPC Mapping hält Wire Schema von Domainmodell getrennt;
- eine Connection erhält nur Events ihrer Subscriptions;
- Responses und Notifications können auf demselben Socket interleaved werden.

### 10.4 Architekturtests

Optional können Importregeln automatisiert werden:

- `domain` importiert weder Pydantic, SQLAlchemy, Dishka, Scheduler noch
  `pyrpckit`;
- `application` importiert weder konkrete Infrastructure Adapter noch
  Presentation Schemas;
- Presentation erstellt keine konkreten Repositories oder Scheduler;
- featureübergreifende konkrete Serviceimporte existieren nur in expliziten
  Integrationsadaptern bzw. am Composition Root.

## 11. Vorgeschlagene Migrationsreihenfolge

Jeder Schritt soll lauffähig bleiben und separat reviewbar sein.

1. **Begriffe festlegen**
   - Entscheiden, ob Automation Session- oder Channel-owned ist.
   - Entscheiden, ob Target eine konkrete Session oder den aktuellen Channel
     meint.
   - RPC-Namespace-Variante beschließen.

2. **Automation Domain einführen**
   - Aggregate, Schedule/Target/Action Values und Domain Exceptions ergänzen.
   - Reine Domain Tests schreiben.
   - Noch keine Storage-Migration.

3. **Scheduler hinter einem Port verstecken**
   - `AutomationRepository` definieren.
   - Scheduler Adapter und Mappings implementieren.
   - `ScheduledJob`, `Trigger`, Codec Envelope und `schema_version` aus
     Application und Presentation entfernen.

4. **Automation Application bereinigen**
   - Use Cases laden Aggregate, rufen Domainmethoden auf und speichern über den
     Port.
   - Ausführung über `AutomationActionExecutor` anbinden.
   - Sessionexistenz bzw. Ownerauflösung explizit prüfen.

5. **Conversation Application aufteilen**
   - Eventtypen aus Domain nach Application verschieben.
   - `TurnLease` aus `SessionRepository` herauslösen.
   - Turn Execution und Task Registry aus `ConversationService` extrahieren.

6. **Connection-Zustand herauslösen**
   - Subscription Registry und Event Forwarder beim WebSocket Adapter
     ansiedeln.
   - Event Publisher und Connection Registry nicht länger in einem Port
     vermischen.

7. **RPC Presentation vereinfachen**
   - Handler nach Feature/Use Case statt mechanisch nach Prefix strukturieren.
   - beschlossene Methodenumbenennung vollständig in OpenRPC und generiertem
     Client durchführen.

8. **Persistenzstrategie neu bewerten**
   - Erst nach der Domainentkopplung entscheiden, ob Scheduler Store genügt
     oder Automation in die Gateway-Datenbank migriert wird.

## 12. Entscheidungen für die Diskussion

Diese Fragen sollten vor der Implementierung beantwortet werden:

1. Gehört eine Automation einer **Session**, einem **Channel** oder einem
   authentifizierten **Account/Principal**?
2. Soll eine Automation nach einem Sessionwechsel weiterlaufen? Wenn ja, muss
   ihr Target wahrscheinlich Channel statt Session sein.
3. Ist `created_from_turn_id` fachlich relevant für Autorisierung/Anzeige oder
   nur Audit-Metadatum?
4. Soll es künftig neben `reminder` weitere Actions geben, zum Beispiel einen
   Tool-Aufruf, eine Nachricht oder ein internes Event?
5. Werden pause/resume, Ausführungshistorie, Fehlerstatus oder einmalige
   Deaktivierung benötigt? Davon hängt das Automation Aggregate ab.
6. Sollen Subscriptions ausschließlich Connection-lokal bleiben oder später
   persistent/geräteübergreifend sein?
7. Bevorzugen wir die bestehenden Resource Prefixes mit `events.*` oder einen
   gemeinsamen `conversation.*`-Namespace?
8. Ist der Scheduler Store mittelfristig Source of Truth oder soll die
   Gateway-Datenbank das Automation-System tragen?

## 13. Vorläufige Empfehlung

Der sinnvollste erste Schnitt ist kein kompletter Rewrite:

- `pyrpckit`, WebSocket und das konkurrierende Senden von Responses und
  Notifications bleiben bestehen.
- `Session` bleibt Conversation Aggregate Root.
- Automation wird ein echtes Aggregate mit Owner, Target, Schedule, Action und
  expliziten Ownership-Regeln.
- Der bestehende Scheduler wird zunächst durch einen Domain-Port verdeckt und
  bleibt Persistence-/Execution-Adapter.
- Subscription wird als flüchtiger Connection-Zustand aus Conversation
  herausgezogen.
- RPC-Namen werden unabhängig von internen Layer-/Dateigrenzen behandelt.
- Erst danach wird entschieden, ob eine eigene Automation-Tabelle und ein
  robustes Multi-Instance-Scheduling nötig sind.

Damit entsteht eine testbare fachliche Mitte, ohne den funktionierenden
Full-Duplex-Transport neu zu erfinden.
