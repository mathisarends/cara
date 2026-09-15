# Wecker als Gateway-Feature

## Zielbild

Cara ist ein persönlicher Voice Assistant. Der Nutzer soll per Sprache Wecker
stellen und bedienen können:

- „Weck mich in 8 Stunden.“
- „Weck mich morgen um 8 Uhr.“
- „Weck mich jeden Wochentag um 5 Uhr.“
- „Noch zehn Minuten.“ / „Stopp, ich bin wach.“
- „Morgen nicht wecken.“ / „Welche Wecker habe ich?“

Das **Weckritual ist vollständig agentisch**. Es gibt keinen Klingelton und
keine Licht- oder Audiologik im Gateway oder im Voice-Client. Zu jedem
fälligen Zeitpunkt startet das Gateway einen Agent-Run, und dessen Payload
verweist auf einen **Routine-Skill** im Workspace. Der Agent lädt den Skill
und führt die Anweisungen für die aktuelle Phase aus, zum Beispiel:

| Phase | Zeitpunkt | Typische Routine (im Skill definiert) |
| --- | --- | --- |
| `pre_wake` | `lead` Minuten vor der Weckzeit | Sonnenaufgang über `huerise` starten, leise Musik über `spoti` |
| `wake` | Weckzeit | Musik lauter, kurze Begrüßung |
| `snooze_end` | Ende der Schlummerzeit | wie `wake`, etwas nachdrücklicher |

Das Gateway besitzt alles, was ein Wecker **deterministisch** können muss:
- Weckzeit, Wiederholung und Vorlauf,
- Aktivieren, Aussetzen, Schlummern und Ausschalten,
- Toleranz nach Ausfällen,
- Persistenz.

Das LLM entscheidet nie, *wann* etwas passiert, sondern nur, *wie* die
Routine ausgeführt wird. Die Routine ändert der Nutzer, indem er den Skill
bearbeitet. Code muss dafür nicht angepasst werden.

## Grundsatzentscheidungen

| Entscheidung | Begründung |
| --- | --- |
| Neues Feature `gateway.features.alarm`, keine Erweiterung von `automation` | Ein Wecker hat Phasen, einen Zustandsautomaten (aktiv/geschlummert/aus), Aussetzen einzelner Termine und eine Verpasst-Regel. `Automation` bleibt „eine Anweisung zu einem Zeitplan“. |
| Payload = Skill-Name + optionale Notiz statt Freitext-Anweisung | Die Routine liegt an einer Stelle (Workspace-Skill) und gilt für alle Wecker. Abweichungen („heute ohne Musik“) stehen in der Notiz des einzelnen Weckers. |
| Ausführung über `TurnService.start_scheduled` | Gleicher Pfad wie bei Automations. Der Wecker ist an die feste `voice`-Channel-Session gebunden (`session.open(channel="voice")`), die der Voice-Client abonniert. Gesprochene Antworten kommen dort an. |
| `libs/scheduler` nur als Timer | Pro Wecker wird immer nur **der nächste fällige Run** als `At`-Trigger armiert. Wiederholung, Zeitumstellung und Aussetzen berechnet die Alarm-Domain, nicht Cron. |
| Keine neuen Gateway-Events | Die Agent-Runs erzeugen bereits Conversation-Events. Wecker-Zustände sind interner Zustand und über `alarm.get`/`alarm.list` abfragbar (siehe `CLAUDE.md`). |
| At-most-once pro Phase | Ein Wecker darf nach einem Absturz nicht zweimal die Routine starten. Der Zustand wird **vor** dem Start des Agent-Runs fortgeschrieben. |
| Huerise läuft außerhalb des Cara-Compose-Stacks | Nur die `huerise`-CLI kommt ins Sandbox-Image. Der Server läuft separat, die CLI erreicht ihn über `host.docker.internal`. |

## Nicht-Ziele (v1)

- Kein Weckton, keine Audio-/Lichtsteuerung im Gateway oder Voice-Client.
- Kein Offline-Wecken im Client bei Gateway-Ausfall.
- Keine Wecker-Events im öffentlichen RPC-Vertrag.
- Keine Mehrgeräte-Logik. Ziel ist genau eine Conversation-Session.
- Keine Änderungen an `gateway.features.automation`.
- Kein Huerise-Service in `compose.yml`.

## Domain-Modell

Pfad: `gateway/src/gateway/features/alarm/domain/`

### Wiederholung

```python
class Weekday(StrEnum):  # MON … SUN


@dataclass(frozen=True, slots=True)
class OnceRecurrence:
    wake_at: datetime                 # timezone-aware, absoluter Zeitpunkt


@dataclass(frozen=True, slots=True)
class WeeklyRecurrence:
    days: frozenset[Weekday]          # nicht leer
    local_time: time                  # Wanduhrzeit ohne tzinfo, Minutenauflösung
    timezone: str                     # IANA, validiert wie CronSchedule


type AlarmRecurrence = OnceRecurrence | WeeklyRecurrence
```

Regeln:

- „In 8 Stunden“ wird beim Anlegen zu `OnceRecurrence(now + 8h)`. Das sind
  echte 8 Stunden, auch über eine Zeitumstellung.
- „Morgen um 8“ wird zu `OnceRecurrence` mit lokaler Zeit plus Zeitzone.
- Wochentage (`WeeklyRecurrence`) werden in lokaler Wanduhrzeit berechnet:
  - Existiert die lokale Zeit wegen Umstellung auf Sommerzeit nicht, gilt der
    erste gültige Zeitpunkt danach (02:30 → 03:30).
  - Ist sie wegen Umstellung auf Winterzeit doppelt, gilt das erste Vorkommen
    (`fold=0`).
- `OnceRecurrence.wake_at` muss bei Create/Update in der Zukunft liegen.

### Routine

```python
@dataclass(frozen=True, slots=True)
class AlarmRoutine:
    skill: str                        # Name eines Workspace-Skills, nicht leer
    note: str | None = None           # optionale Abweichung für diesen Wecker
```

Das Gateway prüft nicht, ob der Skill existiert. Das macht das Agent-Tool beim
Anlegen (siehe Agent).

### Aggregate `Alarm`

`Alarm` ist eine reguläre Klasse mit viel Verhalten, analog zu `Automation`:
private Attribute, Properties, `create(...)`-Classmethod.

| Feld | Bedeutung |
| --- | --- |
| `id`, `created_at`, `owner_id`, `name` | wie `Automation` |
| `target: AlarmTarget` | `SessionTarget(session_id)`, eigene Definition im Alarm-Feature |
| `recurrence: AlarmRecurrence` | |
| `routine: AlarmRoutine` | |
| `pre_wake_lead: timedelta \| None` | 1–120 Minuten; `None` = keine `pre_wake`-Phase |
| `origin: AlarmOrigin` | `created_from_turn_id` |
| `enabled: bool` | Deaktivierte Wecker armieren nichts. |
| `skipped_dates: frozenset[date]` | Lokale Kalendertage (Zeitzone der Wiederholung), deren Termin ausfällt. Vergangene Tage werden beim Fortschreiben entfernt. |
| `occurrence: Occurrence \| None` | Aktueller oder nächster Termin. `None`, wenn deaktiviert oder kein Termin mehr folgt. |

```python
class OccurrenceState(StrEnum):
    UPCOMING = "upcoming"             # Termin berechnet, noch nichts ausgeführt
    PRE_WAKE = "pre_wake"             # Vorlauf-Run gestartet
    ACTIVE = "active"                 # Weck-Run gestartet
    SNOOZED = "snoozed"


@dataclass(frozen=True, slots=True)
class Occurrence:
    wake_at: datetime                 # UTC
    state: OccurrenceState
    snooze_count: int = 0
    snoozed_until: datetime | None = None
    activated_at: datetime | None = None
```

### Phasen und nächster fälliger Run

```python
class AlarmPhase(StrEnum):
    PRE_WAKE = "pre_wake"
    WAKE = "wake"
    SNOOZE_END = "snooze_end"


@dataclass(frozen=True, slots=True)
class DueRun:
    alarm_id: UUID
    phase: AlarmPhase
    due_at: datetime                  # UTC
    wake_at: datetime                 # UTC, Termin, zu dem der Run gehört
```

`Alarm.next_due_run(now) -> DueRun | None`:

| Zustand | Nächster Run |
| --- | --- |
| `UPCOMING` mit `pre_wake_lead` | `PRE_WAKE` zu `max(wake_at - lead, now)` |
| `UPCOMING` ohne `pre_wake_lead` | `WAKE` zu `wake_at` |
| `PRE_WAKE` | `WAKE` zu `wake_at` |
| `SNOOZED` | `SNOOZE_END` zu `snoozed_until` |
| `ACTIVE` | kein Run. Das Gateway armiert einen internen Auto-Close-Timer zu `activated_at + ACTIVE_TIMEOUT`. |

Der Vorlauf wird verkürzt, wenn er beim Anlegen nicht mehr vollständig
hineinpasst. Beispiel: „Weck mich in 20 Minuten“ bei 30 Minuten Vorlauf startet
`pre_wake` sofort. Der Run-Prompt meldet dann 20 verbleibende Minuten.

### Zustandsautomat eines Termins

```text
UPCOMING ──pre-wake fällig──▶ PRE_WAKE ──wake fällig──▶ ACTIVE
UPCOMING ──wake fällig (kein Vorlauf)──────────────────▶ ACTIVE
ACTIVE   ──snooze(minutes)──▶ SNOOZED ──snooze-Ende fällig──▶ ACTIVE
PRE_WAKE | ACTIVE | SNOOZED ──dismiss──▶ (Termin beendet)
ACTIVE | SNOOZED ──ACTIVE_TIMEOUT ohne dismiss──▶ (Termin beendet)
UPCOMING | PRE_WAKE ──Weckzeit länger als MISSED_GRACE her──▶ (Termin verpasst)
```

„Termin beendet/verpasst“ bedeutet:

- `OnceRecurrence`: Der Wecker wird gelöscht (wie ein einmaliges `Automation`).
- `WeeklyRecurrence`: Der nächste Termin nach dem beendeten `wake_at` wird als
  `UPCOMING` berechnet. `skipped_dates` werden dabei übersprungen und
  verbrauchte Einträge entfernt.

Domain-Methoden (alle validieren den Zustand und werfen Domain-Fehler):

| Methode | Erlaubt in | Wirkung |
| --- | --- | --- |
| `start_run(run, now)` | passender Zustand und `run` entspricht `next_due_run` | Übergang laut Automat |
| `snooze(duration, now)` | `ACTIVE`, `SNOOZED` | `SNOOZED`, `snoozed_until = now + duration`, `snooze_count += 1` |
| `dismiss(now)` | `PRE_WAKE`, `ACTIVE`, `SNOOZED` | Termin beendet |
| `skip_next()` | `UPCOMING` | Fügt den lokalen Tag des nächsten Termins zu `skipped_dates` hinzu und berechnet neu. Bei `OnceRecurrence`: Fehler, stattdessen löschen. |
| `set_enabled(flag, now)` | immer | `False` → `occurrence = None`. `True` → neu berechnen ab `now`. |
| `update(...)` | immer | Ersetzt Wiederholung, Routine, Vorlauf und Name. Setzt `occurrence` neu ab `now` und leert `skipped_dates`. |
| `expire(now)` | `ACTIVE`/`SNOOZED` nach Timeout, `UPCOMING`/`PRE_WAKE` nach `MISSED_GRACE` | Termin beendet bzw. verpasst |

Konstanten in `domain` (in v1 keine Konfiguration):

```python
MISSED_GRACE = timedelta(minutes=15)
ACTIVE_TIMEOUT = timedelta(minutes=60)
MAX_SNOOZE = timedelta(minutes=60)
```

Fehler (`domain/errors.py`):
- `AlarmNotFoundError`
- `AlarmStateError`, z. B. Schlummern ohne aktiven Termin
- `InvalidAlarmError`: leere Wochentage, Weckzeit in der Vergangenheit, Vorlauf
  außerhalb des Bereichs, unbekannte Zeitzone, leerer Skill-Name

## Application

Pfad: `gateway/src/gateway/features/alarm/application/`

### Ports (`ports.py`)

```python
class AlarmTargetResolver(ABC):
    @abstractmethod
    async def require(self, target: AlarmTarget) -> None: ...


class AlarmRunExecutor(ABC):
    @abstractmethod
    async def execute(self, alarm: Alarm, run: DueRun, now: datetime) -> None: ...


class AlarmScheduler(ABC):
    """Runtime timer for persisted alarms; it never owns their state."""

    @abstractmethod
    def arm(self, alarm: Alarm, now: datetime) -> None:
        """Replace the pending timer with the alarm's next due run or expiry."""

    @abstractmethod
    def disarm(self, alarm_id: UUID) -> None:
        """Remove the pending timer. Never cancels an agent run already started."""
```

Die aktuelle Zeit kommt als `now`-Parameter bzw. über einen injizierbaren
Clock-Port, damit Tests deterministisch sind.

### `AlarmService`

Methoden: `list`, `get`, `create`, `update`, `delete`, `set_enabled`,
`skip_next`, `snooze`, `dismiss`, `resume`.

- Owner-Prüfung wie `AutomationService.get` (fremde IDs → `AlarmNotFoundError`).
- Jede Mutation folgt dem Muster „laden → Domain-Methode → speichern →
  `scheduler.arm`“. Bei Löschung: `disarm` → entfernen.
- `resume()` beim Start: Jeder gespeicherte Wecker wird armiert. Überfällige
  Runs landen sofort in der Execution und unterliegen dort den
  Toleranzregeln.

### `AlarmExecution`

Wird vom Scheduler-Runner mit einem `DueRun` bzw. einem Expiry-Timer
aufgerufen:

1. Wecker laden. Fehlt er → Ende.
2. **Stale-Check:** Entspricht der Run nicht mehr `alarm.next_due_run(now)`
   (weil der Wecker inzwischen geändert, geschlummert oder ausgeschaltet wurde),
   passiert nichts.
3. **Toleranzregeln:**
   - `PRE_WAKE` und `now >= wake_at`: Vorlauf überspringen, Zustand auf
     `PRE_WAKE` setzen (ohne Agent-Run) und den `WAKE`-Run armieren.
   - `WAKE`/`SNOOZE_END` und `now - due_at > MISSED_GRACE`: `expire(now)`,
     loggen (`warning`), speichern, armieren, **kein** Agent-Run.
4. `alarm.start_run(run, now)`, speichern und nächsten Timer armieren,
   **bevor** der Agent-Run startet (at-most-once).
5. `executor.execute(alarm, run, now)`. Fehler werden geloggt. Der Zustand
   wird nicht zurückgedreht.

Expiry-Timer (`ACTIVE_TIMEOUT`) rufen `expire(now)` auf und armieren den
nächsten Termin, ohne Agent-Run.

## Infrastructure

Pfad: `gateway/src/gateway/features/alarm/infrastructure/`

### Scheduling (`scheduling.py`)

Das Feature erzeugt eine eigene `Scheduler[AlarmJob]`-Instanz im
`AlarmProvider`, analog zu `AutomationProvider.scheduler`.

**Wichtige Falle:** `Scheduler.schedule(job_id, …)` ruft `remove(job_id)` auf
und bricht damit die laufende Task desselben Jobs ab. Armiert die Execution
den nächsten Run unter derselben Job-ID aus dem laufenden Runner heraus,
bricht sie sich selbst ab. Deshalb:

- Die Job-ID ist pro Run eindeutig, z. B.
  `f"alarm:{alarm_id}:{phase}:{due_at.isoformat()}"`.
- `InProcessAlarmScheduler` merkt sich pro `alarm_id` die aktuell **armierte**
  Job-ID. `arm` entfernt nur diese und plant die neue ein.
- Der Runner entfernt die Zuordnung, sobald ein Run startet. So entfernt
  `disarm` (etwa über `dismiss` aus einem anderen Turn) nie einen bereits
  laufenden Agent-Run.

### Conversation-Adapter (`conversation.py`)

`ConversationAlarmTargetResolver` funktioniert wie das Automation-Pendant.

`ConversationAlarmRunExecutor` ruft `TurnService.start_scheduled` mit folgenden
Werten auf:

```python
metadata = {
    "origin": "alarm",
    "alarm_id": str(alarm.id),
    "alarm_phase": run.phase,
    "wake_at": run.wake_at.isoformat(),
    "scheduled_for": run.due_at.isoformat(),
}
```

Prompt-Wrapper. Er liefert die berechneten Fakten, damit der Skill die
Routine relativ formulieren kann (z. B. „Sonnenaufgang über die verbleibenden
Minuten“) und für jede Wiederholung korrekt bleibt:

```text
[Scheduled alarm run]
Alarm: <name or id>
Phase: pre_wake | wake | snooze_end
Wake time: 2026-09-16 06:00 (Tuesday, Europe/Berlin)
Current local time: 2026-09-16 05:30
Minutes until wake time: 30                     # nur pre_wake
Snooze count: 2                                 # nur snooze_end
Routine note: <note>                            # nur wenn gesetzt
Load the skill "<routine.skill>" now and carry out its instructions for this
phase. The routine note, if present, takes precedence over the skill defaults.
Start long-running effects (such as a sunrise or music) so that they continue on
their devices, and return without waiting for them to finish.
Do not create, update, snooze, skip or dismiss alarms in this run.
```

Die lokale Zeitzone ist die der `WeeklyRecurrence` bzw. bei `OnceRecurrence`
die konfigurierte `agent.timezone` aus `gateway.yaml`.

### Persistenz

- Tabelle `gateway_alarms` (`orm.py`), Migration
  `gateway/migrations/versions/0011_alarms.py` mit `down_revision = "0010"`.
- Spalten flach wie bei `gateway_automations`:
  - Basis: `owner_id` (Index), `name`, `target_kind`, `target_session_id`
  - Wiederholung: `recurrence_kind`, `once_wake_at`, `weekly_days` (String, z. B.
    `"mon,tue,wed"`), `weekly_local_time` (String `"HH:MM"`), `weekly_timezone`
  - Routine: `routine_skill`, `routine_note`, `pre_wake_lead_seconds`
  - Status: `enabled`, `skipped_dates` (String, ISO-Daten kommagetrennt),
    `created_from_turn_id`
  - Termin: `occurrence_wake_at`, `occurrence_state`,
    `occurrence_snooze_count`, `occurrence_snoozed_until`,
    `occurrence_activated_at`
- Alle Zeitpunkte als `DateTime(timezone=True)`.
- `SQLAlarmRepository` nach dem Muster von `SQLAutomationRepository`, inklusive
  Migrationstest.

## Presentation

Pfad: `gateway/src/gateway/features/alarm/presentation/`. Die Feature-
Registrierung erfolgt analog zu `automation/feature.py` in
`gateway.features.FEATURES`. In `app.py` kommt ein OpenAPI-Tag `alarms` dazu.

### JSON-RPC (`rpc/`)

```text
alarm.list        (owner_id)                                     -> { alarms }
alarm.get         (owner_id, alarm_id)                           -> Alarm
alarm.create      (owner_id, target, recurrence, routine,
                   pre_wake_minutes?, name?, created_from_turn_id) -> Alarm
alarm.update      (owner_id, alarm_id, recurrence, routine,
                   pre_wake_minutes?, name?, created_from_turn_id) -> Alarm
alarm.delete      (owner_id, alarm_id)                           -> { deleted }
alarm.set_enabled (owner_id, alarm_id, enabled)                  -> Alarm
alarm.skip_next   (owner_id, alarm_id)                           -> Alarm
alarm.snooze      (owner_id, alarm_id, minutes: 1..60)           -> Alarm
alarm.dismiss     (owner_id, alarm_id)                           -> { alarm: Alarm | null }
```

Modelle (`RpcModel`, Wiederholung diskriminiert über `kind`):

```text
OnceRecurrence   { kind: "once",   wake_at: datetime }
WeeklyRecurrence { kind: "weekly", days: ["mon", …], local_time: "HH:MM", timezone }
AlarmRoutine     { skill: str (min_length=1), note: str | null }
AlarmOccurrence  { wake_at, state, snooze_count, snoozed_until }
AlarmResponse    { id, owner_id, name, created_at, enabled, target, recurrence,
                   routine, pre_wake_minutes, created_from_turn_id,
                   skipped_dates, occurrence, next_run: { phase, due_at } | null }
```

`alarm.dismiss` auf einen einmaligen Wecker löscht ihn und liefert
`{ alarm: null }`.

Error-Mapping:

- `AlarmNotFoundError` → `ResourceNotFoundError` / 404 `alarm_not_found`
- `AlarmStateError` → `RpcInvalidParamsError` / 409 `alarm_state_conflict`
- `InvalidAlarmError` → `RpcInvalidParamsError` / 422
- Beim Create zusätzlich `SESSION_NOT_FOUND`, wie bei Automation

### REST

Spiegelt die RPC-Methoden unter `/v1/owners/{owner_id}/alarms`, analog zu
`automation_router`. Aktionen als `POST /{alarm_id}/snooze`, `/dismiss`,
`/skip-next`, `PUT /{alarm_id}/enabled`.

### Generierte Artefakte

Danach Schema und Client neu erzeugen (CI prüft Drift):

```bash
uv run --package gateway-server cara-gateway-schema
uv run --package gateway-server cara-gateway-client-generate gateway/schema/gateway.openrpc.json
```

## Agent

### Port (`agent/src/agent/tools/handler/ports.py`)

```python
@dataclass(frozen=True, slots=True)
class WakeOnce:
    when: datetime


@dataclass(frozen=True, slots=True)
class WakeWeekly:
    days: frozenset[str]              # "mon" … "sun"
    local_time: time
    timezone: str


type AlarmRecurrence = WakeOnce | WakeWeekly


@dataclass(frozen=True, slots=True)
class Alarm:
    id: UUID
    name: str | None
    enabled: bool
    recurrence: AlarmRecurrence
    skill: str
    note: str | None
    pre_wake_minutes: int | None
    skipped_dates: tuple[date, ...]
    state: str | None                 # upcoming | pre_wake | active | snoozed
    next_wake_at: datetime | None
    snoozed_until: datetime | None


class Alarms(ABC):
    """Alarms of the owner, created against the conversation the agent runs in."""

    @abstractmethod
    async def list(self) -> tuple[Alarm, ...]: ...
    @abstractmethod
    async def create(self, *, recurrence, skill, note, pre_wake_minutes, name) -> Alarm: ...
    @abstractmethod
    async def update(self, alarm_id, *, recurrence, skill, note, pre_wake_minutes, name) -> Alarm: ...
    @abstractmethod
    async def delete(self, alarm_id: UUID) -> None: ...
    @abstractmethod
    async def set_enabled(self, alarm_id: UUID, enabled: bool) -> Alarm: ...
    @abstractmethod
    async def skip_next(self, alarm_id: UUID) -> Alarm: ...
    @abstractmethod
    async def snooze(self, alarm_id: UUID, minutes: int) -> Alarm: ...
    @abstractmethod
    async def dismiss(self, alarm_id: UUID) -> Alarm | None: ...
```

### Handler (`agent/src/agent/tools/handler/gateway_alarms.py`)

`GatewayAlarms(Alarms)` nutzt dieselbe `GatewayConnection` wie
`GatewayReminders`, ebenso `_client()`-Kontextmanager und Fehlerabbildung auf
`ToolError`. Die Instanz wird in `cara_runtime._turn_tool_dependencies` neben
`GatewayReminders` erzeugt. `GatewayAlarms` wird in
`agent/tools/handler/__init__.py` exportiert, die Datentypen nur, soweit die
Tools sie brauchen.

### Tools (`agent/src/agent/tools/actions/alarms.py`)

Registriert über `register_alarm_tools` in `actions/__init__.py`, verfügbar
mit `provided(Alarms)`.

| Tool | Parameter | Hinweis |
| --- | --- | --- |
| `list_alarms` | – | Pro Wecker: ID, Label, Wiederholung, Skill, Notiz, Zustand, nächste Weckzeit mit Wochentag |
| `set_alarm` | genau eines von `in_minutes` \| `wake_at` (lokale Wanduhrzeit) \| `weekly` (`days`, `local_time`); `timezone?`, `skill` (Default `"wake-up"`), `note?`, `pre_wake_minutes` (Default 30, `0` = kein Vorlauf), `name?` | `in_minutes` wird gegen `LocalClock` in einen absoluten Zeitpunkt umgerechnet. |
| `update_alarm` | `alarm_id` + dieselben Felder wie `set_alarm` | Ersetzt den kompletten Wecker |
| `delete_alarm` | `alarm_id` | |
| `set_alarm_enabled` | `alarm_id`, `enabled` | |
| `skip_next_alarm` | `alarm_id` | |
| `snooze_alarm` | `alarm_id?`, `minutes` (Default 9) | Ohne ID: genau der eine Wecker im Zustand `active`/`snoozed`, sonst `ToolError` mit Kandidaten |
| `dismiss_alarm` | `alarm_id?` | Ohne ID: genau der eine Wecker im Zustand `pre_wake`/`active`/`snoozed` |

Skill-Validierung in `set_alarm`/`update_alarm`: Das Tool bekommt zusätzlich
`Inject[Skills]`, ruft `skills.refresh_if_changed()` und dann
`skills.get(skill)` auf. Ein `ValueError` wird zu `ToolError` mit der Liste
der verfügbaren Skills. Ein Wecker mit falschem Skill-Namen darf nicht erst
um 5 Uhr morgens scheitern.

Tool-Antworten nennen immer **Wochentag, Datum, lokale Uhrzeit und die Zeit bis
dahin**, z. B. `Scheduled: <id> 'Wecker' — Dienstag 16.09. 06:42 (in 8 h 0 min),
Vorlauf 30 min, Routine wake-up`. So bestätigt der Assistent die effektive
Zeit und Fehler fallen sofort auf.

Tool-Beschreibungen enthalten die Regeln, die sonst ein eigener Skill
bräuchte:

- Vor relativen Zeitangaben `current_time` aufrufen. „Morgen“ zwischen 00:00
  und 04:59 meint im Zweifel den heute beginnenden Morgen, bei Unklarheit kurz
  nachfragen.
- Jeder Weckwunsch nutzt `set_alarm`, nicht `create_reminder`.
- Nach dem Anlegen nur die effektive Weckzeit bestätigen und die Routine
  **nicht** testen.
- `snooze_alarm`/`dismiss_alarm` ändern nur den Wecker. Musik und Licht
  passt der Agent im selben Turn laut Routine-Skill an (Abschnitt „Stop“ bzw.
  „Snooze“).

Validierung im Tool:

- Zeitpunkt in der Vergangenheit → `ToolError` mit aktueller lokaler Zeit (wie
  `reminders._schedule`).
- Leere `days`, unbekannte Wochentage, Zeitzone nicht auflösbar oder mehr als
  eine bzw. keine Zeitvariante → `ToolError`.

## Huerise-Integration (Sonnenaufgang)

[Huerise](https://github.com/mathisarends/huerise) ist ein eigenständiger
Server mit Go-CLI. `huerise start` antwortet sofort (`202`), die
Helligkeitsrampe läuft serverseitig im Hintergrund. Damit blockiert der
`pre_wake`-Run nicht. Relevante Befehle:

```bash
huerise start --duration-seconds <n> --json --compact   # 409, wenn bereits aktiv
huerise stop                                            # idempotent, Licht bleibt stehen
huerise doctor
```

### Im Repo (Teil der Implementierung)

`docker/tools.txt` bekommt einen Eintrag:

```text
huerise   github.com/mathisarends/huerise/cli/cmd/huerise    v0.0.0-20260901065008-07186f3228bc
```

Das Go-Modul liegt im Unterordner `cli/`. Die Repo-Tags (`v0.1.1`) haben kein
`cli/`-Präfix, deshalb ist eine Pseudo-Version nötig. Diese entspricht dem
Commit von `v0.1.1` und ist auf `proxy.golang.org` auflösbar. `compose.yml`
bleibt unverändert.

### Setup beim Nutzer (manuell, nicht Teil der Implementierung)

1. Huerise mit dem eigenen Compose-Stack starten. Dabei `HUERISE_PORT=8010`
   setzen, weil `8000` bereits das Gateway belegt.
2. Die CLI-Konfiguration für die Sandbox anlegen:
   `${CARA_SANDBOX_CLI_CONFIG_ROOT:-~/.cara/cli-config}/huerise/.env`

   ```dotenv
   HUERISE_API_URL=http://host.docker.internal:8010
   HUERISE_API_KEY=<derselbe Key wie im Huerise-Server>
   ```

   In der Sandbox liegt die Datei unter `/tmp/.config/huerise/.env`.
   `host.docker.internal` löst im Sandbox-Image auf (geprüft).
3. `bash scripts/setup/prepare_bash_sandbox.sh` ausführen. Das Skript baut das
   Image neu und legt den Stub-Skill `skills/huerise/SKILL.md` an, sofern er
   fehlt.
4. Die Skills `huerise` und `wake-up` im Workspace anlegen bzw. ergänzen
   (Entwürfe siehe Anhang).

## Tests

Gateway (`gateway/tests/features/alarm/`):

- **Domain / Wiederholung**
  - Nächster Wochentagstermin über Wochenende und Monatswechsel.
  - Sommerzeit-Lücke (Europe/Berlin, 02:30 am Umstellungstag → 03:30).
  - Winterzeit-Doppelung (`fold=0`).
  - `skipped_dates` überspringt genau einen Termin und wird danach bereinigt.
- **Domain / Zustandsautomat**
  - Alle erlaubten Übergänge.
  - Verbotene Übergänge werfen `AlarmStateError`.
  - `snooze` erhöht `snooze_count`.
  - `dismiss` aus `PRE_WAKE` beendet den Termin ohne Weck-Run.
- **Domain / Vorlauf**
  - Verkürzter Vorlauf, wenn die Weckzeit näher liegt als `lead`.
  - Kein `PRE_WAKE`, wenn `pre_wake_lead` `None` ist.
  - Vorlauf überspringen, wenn der Run erst nach der Weckzeit ausgeführt wird.
- **Execution**
  - Stale-Runs nach `update`/`dismiss` lösen nichts aus.
  - `MISSED_GRACE`: 10 Minuten zu spät → Run, 20 Minuten zu spät → verpasst,
    kein Run, nächster Termin berechnet.
  - Zustand ist gespeichert, bevor der Executor aufgerufen wird. Ein
    fehlschlagender Executor führt nicht zu einem erneuten Run.
  - `ACTIVE_TIMEOUT` beendet den Termin.
  - Einmaliger Wecker wird nach `dismiss`/Verpassen gelöscht.
- **Scheduling (mit echtem `Scheduler`, wie `test_scheduling.py`)**
  - `pre_wake` → `wake` → Schlummern → `snooze_end` laufen in Reihenfolge und
    mit korrekter Phase-Metadata.
  - Armieren des nächsten Runs aus einem laufenden Run bricht diesen nicht ab.
  - `disarm` während eines laufenden Runs bricht ihn nicht ab.
  - `resume()` nach „Neustart“ mit überfälligem Run beachtet die Toleranzregeln.
- **Repository / Migration:** Round-Trip aller Felder, Migration `0011`
  up/down.
- **RPC / REST:** Validierung (leere Tage, Vergangenheit, `pre_wake_minutes`
  außerhalb 1–120, `minutes` außerhalb 1–60, leerer Skill), Owner-Isolation,
  Error-Codes.
- **Prompt-Wrapper:** Enthält Phase, lokale Weckzeit mit Wochentag,
  Restminuten (nur `pre_wake`), Skill-Name und Notiz (nur wenn gesetzt).

Agent (`agent/tests/`):

- `set_alarm` mit `in_minutes`, `wake_at` und `weekly`; genau eine Variante
  erzwungen; Vergangenheit abgelehnt.
- Unbekannter Skill → `ToolError` mit verfügbaren Skills.
- `pre_wake_minutes=0` erzeugt einen Wecker ohne Vorlauf.
- `snooze_alarm`/`dismiss_alarm` ohne ID: eindeutiger aktiver Wecker gefunden,
  bei 0 oder >1 `ToolError`.
- `GatewayAlarms` Mapping gegen generierte Client-Modelle (analog
  `test_gateway_reminders.py`).
- Tool-Ausgabe enthält Wochentag und die Zeit bis zum Wecken.

## Umsetzungsreihenfolge

1. Domain inkl. Wiederholung, Zustandsautomat und Tests.
2. Repository, ORM und Migration `0011`.
3. Application (`AlarmService`, `AlarmExecution`) mit Fakes.
4. Infrastructure: Scheduler-Adapter mit eindeutigen Job-IDs,
   Conversation-Executor, Provider.
5. Presentation: RPC, REST, Error-Mapping, Feature-Registrierung; Schema und
   Client neu generieren.
6. Agent: Port, `GatewayAlarms`, Tools inkl. Skill-Validierung, Wiring in
   `cara_runtime.py`.
7. `docker/tools.txt` um `huerise` ergänzen.

## Akzeptanzkriterien

- „Weck mich in 8 Stunden“ in der `voice`-Session erzeugt genau einen Wecker
  mit Routine `wake-up` und 30 Minuten Vorlauf. Der Assistent bestätigt
  Wochentag und Uhrzeit.
- 30 Minuten vor der Weckzeit startet ein Agent-Run mit Phase `pre_wake`, der
  den Routine-Skill lädt. Zur Weckzeit folgt ein Run mit Phase `wake`. Jeder
  läuft pro Termin höchstens einmal.
- „Jeden Wochentag um 5 Uhr“ weckt Montag bis Freitag um 05:00 Europe/Berlin,
  auch über Zeitumstellungen hinweg.
- „Morgen nicht wecken“ lässt genau den nächsten Termin ausfallen.
- „Noch 10 Minuten“ startet 10 Minuten später einen Run mit Phase
  `snooze_end`. „Stopp“ beendet den Termin, danach folgt kein Run mehr.
- Ein Gateway-Neustart innerhalb von 15 Minuten nach der Weckzeit weckt noch.
  Ein späterer Neustart weckt nicht nachträglich, sondern plant den nächsten
  Termin.
- Ein Wecker mit unbekanntem Skill wird beim Anlegen abgelehnt.
- `huerise --help` läuft im neu gebauten Sandbox-Image (Verifikation in
  `prepare_bash_sandbox.sh`).
- `automation` bleibt unverändert. Alle bestehenden Tests sowie Schema-Drift-,
  Lint- und Typecheck-CI sind grün.

## Offene Punkte

- **Spotify-Ausgabegerät:** Spotify Connect über `spoti --device`. Taucht die
  Sonos Era 100 als Connect-Gerät zuverlässig auf, wenn sie vorher inaktiv
  war? Falls nicht, braucht der Skill `sonos open <spotify-uri>` als Fallback.
- **Laufender Turn zur Weckzeit:** `start_scheduled` wartet auf die
  Session-Lease. Spricht der Nutzer zur Weckzeit gerade mit Cara, startet die
  Routine verzögert. Für v1 akzeptiert.

## Anhang: Skill-Entwürfe (Workspace, nicht Repo)

### `skills/wake-up/SKILL.md`

```markdown
---
name: wake-up
description: Morning wake-up routine executed by scheduled alarm runs (sunrise light, music, greeting), and how to stop or snooze an active alarm.
metadata:
  status: ready
---

# Wake-up routine

Scheduled alarm runs state a `Phase`. Follow only the section for that phase.
A `Routine note` in the run prompt overrides these defaults. Speak short,
friendly German. Never wait for light or music effects to finish.

## Phase pre_wake

1. Start the sunrise over the remaining time:
   `huerise --env-file /tmp/.config/huerise/.env start --duration-seconds <Minutes until wake time × 60> --json --compact`.
   A `409` means a sunrise is already running; continue.
2. Start quiet music with `spoti`: `<playlist or track URI>` on `<device>`,
   volume `<5–10>`.
3. Do not speak.

## Phase wake

1. If music is playing, raise the volume to `<25>`; otherwise start
   `<playlist or track URI>` on `<device>` at that volume.
2. Greet the user in one or two sentences with the time and today's weather.

## Phase snooze_end

Like `wake`, with volume `<30>`, and without repeating the weather.

## Stop ("Stopp", "ich bin wach")

Pause Spotify, run `huerise --env-file /tmp/.config/huerise/.env stop` (the
lights stay at their current level), then call `dismiss_alarm`.

## Snooze ("noch X Minuten")

Pause Spotify, leave the lights as they are, then call `snooze_alarm` with the
requested minutes.
```

### `skills/huerise/SKILL.md`

Wird von `prepare_bash_sandbox.sh` als Bootstrap-Stub angelegt und beim ersten
Gebrauch vom Agent dokumentiert. Pflichtinhalt, damit er zur Routine passt:

- Jeder Aufruf mit `--env-file /tmp/.config/huerise/.env`.
- `start [--duration-seconds N]`, `stop`, `doctor`, `configuration show`.
- `--json --compact` für Agent-Aufrufe, niemals `--watch`.
- Exit-Codes `0`/`1`/`2`/`3` und `409` bei bereits laufendem Sonnenaufgang.
