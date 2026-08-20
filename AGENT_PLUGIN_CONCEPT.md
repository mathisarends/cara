# Konzept: Agent-Plugins für das Gateway

## Ziel

Das Gateway soll eine Agent-Runtime über Konfiguration auswählen und aus einem
normal installierten Python-Paket laden können. Ein Plugin liefert ausschließlich
die Ausführung eines Agent-Turns. WebSocket-Protokoll, Sessions, Persistenz,
Nebenläufigkeit und die Übersetzung in Gateway-Events bleiben beim Gateway.

Für den ersten Schritt sollte pro Gateway-Prozess genau **ein** Agent-Plugin aktiv
sein. Routing zwischen mehreren Agenten kann später ergänzt werden, ohne den
Plugin-Vertrag zu ändern.

```text
Voice-/CLI-Client
       │ JSON-RPC/WebSocket
       ▼
Gateway: Channel auf Session auflösen
       │ session_id + neue Nachricht
       ▼
Gateway ConversationService + Session Store
       │ AgentRunRequest(session_id, channel, input)
       ▼
konfiguriertes AgentRunner-Plugin
       │ lädt Kontext bei Bedarf über SessionReader
       ▼
Cara Agent + Modelle + Tools + Skills
```

Die Voice-Pipeline selbst läuft dabei weiterhin als Client des Gateways. Das
Plugin kapselt den heutigen `agent.Agent`; Mikrofon, STT und TTS gehören nicht in
den Gateway-Prozess.

## Abgleich mit OpenClaw

OpenClaw trennt ebenfalls zwischen Channel, Gateway-Session und Agent-Runtime:

- Ein Channel liefert Absender-, Account- und Chat-Kontext.
- Das Gateway leitet daraus einen kanonischen Session-Key ab und löst ihn auf
  eine persistierte Session auf.
- Der Client sendet anschließend eine neue Nachricht gegen diese Session, nicht
  bei jedem Turn den kompletten bisherigen Transcript.
- In der aktuellen Database-first-Architektur werden intern insbesondere
  `{agentId, sessionId}` weitergereicht. Der Runner öffnet den Transcript-Kontext
  anhand dieser Identität.

Das ist in der
[Session-Key-Auflösung](https://github.com/openclaw/openclaw/blob/main/src/config/sessions/session-key.ts),
im [Gateway-Protokoll](https://github.com/openclaw/openclaw/blob/main/docs/gateway/protocol.md)
und im
[Database-first-Konzept](https://github.com/openclaw/openclaw/blob/main/docs/refactor/database-first.md)
zu sehen.

Cara sollte das Prinzip übernehmen, aber nicht OpenClaws gesamtes Multi-Agent-
Routing kopieren. Insbesondere bleibt bei Cara das Gateway alleiniger Owner von
Session und Transcript. Das Agent-Plugin bekommt nur eine Session-Referenz und
eine schmale Lese-Schnittstelle auf den dafür benötigten Kontext.

## Warum der bestehende Port noch nicht genügt

`AgentRunner` ist bereits der richtige Austauschpunkt. Seine aktuelle Methode

```python
run(session_id, metadata)
```

erhält jedoch nicht einmal den aktuellen Benutzertext. Die Lösung ist nicht, die
gesamte History in jeden Aufruf zu kopieren. Stattdessen erhält der Runner eine
Session-Referenz und kann den benötigten Kontext über einen vom Gateway
bereitgestellten `SessionReader` laden. Außerdem
enthalten die heutigen `voice.llm`-Tool-Events keine Call-ID, Argumente oder
Ergebnisse, die das Gateway zum Persistieren benötigt.

Darum sollte das Gateway eine kleine, eigenständige Plugin-API besitzen. Der
bestehende Agent bekommt einen Adapter auf diese API; die Voice-Events sind nicht
der Plugin-Vertrag.

## Öffentliche Plugin-API

Die API sollte als kleines Paket `agent-plugin-api` ohne FastAPI-, Dishka- oder
SQL-Abhängigkeiten angelegt werden. Damit hängt ein Plugin nur am stabilen
Vertrag und nicht an der Gateway-Implementierung. Das Gateway selbst implementiert
die darin definierten Ports.

```python
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AgentChannelRef:
    name: str                    # "voice", "cli", später z. B. "telegram"
    account_id: str | None = None


@dataclass(frozen=True, slots=True)
class AgentSessionRef:
    id: UUID
    channel: AgentChannelRef


@dataclass(frozen=True, slots=True)
class AgentRunRequest:
    session: AgentSessionRef
    turn_id: UUID
    input_id: UUID
    input: str
    turn_metadata: Mapping[str, Any] = field(default_factory=dict)


class AgentSessionReader(Protocol):
    async def context_for_turn(
        self,
        session_id: UUID,
        input_id: UUID,
    ) -> "AgentContext": ...


@dataclass(frozen=True, slots=True)
class AgentPluginContext:
    sessions: AgentSessionReader


class AgentRunner(Protocol):
    def run(self, request: AgentRunRequest) -> AsyncIterator[AgentEvent]: ...

    async def close(self) -> None: ...


class AgentPlugin(Protocol):
    api_version: int

    def create(
        self,
        config: Mapping[str, Any],
        context: AgentPluginContext,
    ) -> AgentRunner: ...
```

`AgentEvent` bleibt die bestehende, gateway-eigene Union aus
`ChatDelta`, `ChatCompleted`, `ToolCallStarted` und `ToolCallCompleted`.
Plugin-Pakete importieren nur diese öffentliche API, niemals
`ConversationService`, Repository-Klassen oder Dishka.

`AgentContext` ist eine typisierte, read-only Sicht auf frühere User-Nachrichten,
Assistant-Nachrichten und Tool-Call-Sequenzen. `context_for_turn()` liefert nur
Einträge **vor** `input_id`; dadurch taucht die aktuelle Eingabe nicht doppelt
auf. Ob das Gateway später komprimierten statt vollständigen Kontext liefert,
bleibt eine interne Entscheidung und ändert den Plugin-Aufruf nicht.

Wichtig: Der Reader ist eine Capability des Gateways, kein SQL-Repository. Das
Plugin kann damit weder Sessions erstellen noch beliebige Daten speichern.

## Verständlicher Ablauf eines Turns

```text
1. Voice öffnet "voice/local" beim Gateway
2. Gateway löst oder erstellt die Session und gibt session_id zurück
3. Voice sendet turn.start(session_id, "Wie spät ist es?")
4. Gateway sperrt die Session und speichert die User-Nachricht
5. Gateway ruft das Plugin mit session_id, channel, input_id und Text auf
6. Plugin lädt bei Bedarf den früheren Kontext über SessionReader
7. Plugin streamt Chat- und Tool-Events
8. Gateway persistiert diese Events und veröffentlicht sie an Voice
9. Gateway beendet den Turn und gibt die Session wieder frei
```

Der Client kennt also keine History. Das Plugin besitzt keine Session. Nur das
Gateway erzeugt, sperrt, persistiert, liest und beendet Sessions.

## Channel und Session-Auflösung

Für Cara genügt zunächst ein kleineres Modell als bei OpenClaw:

```python
session = await gateway.sessions.open(
    channel=ChannelRef(name="voice", account_id="local")
)
```

`session.open` ist idempotent: Das Gateway bildet aus dem normalisierten
`ChannelRef` einen internen, eindeutigen Route-Key und gibt eine vorhandene
Session zurück oder erstellt selbst eine neue UUID. Für einen bewusst neuen
Dialog kann später `session.reset` oder `session.create_new` angeboten werden.

Für Version 1 können Voice und CLI auch weiterhin explizit `session.create`
verwenden. Entscheidend ist, dass die UUID immer vom Gateway stammt, der Channel
als eigenes typisiertes Feld an der Session persistiert wird und nicht als
beliebiger Metadata-Eintrag versteckt ist.

Der Route-Key ist intern. Externe Clients arbeiten mit der opaken `session_id`;
sie dürfen keine frei erfundenen Session-Keys verwenden. Das vermeidet zugleich
Cross-Session-Zugriffe, wenn später Authentifizierung hinzukommt.

## Discovery über Python Entry Points

Entry Points sind hier geeigneter als frei konfigurierte Import-Strings:

- das Plugin kann als eigenes Wheel installiert werden;
- das Gateway muss dessen Quellcode nicht kennen oder ändern;
- Namen und Duplikate lassen sich beim Start eindeutig validieren;
- der Mechanismus funktioniert sowohl mit PyPI-Paketen als auch mit lokalen
  `uv`-Workspace-Abhängigkeiten.

Ein Plugin deklariert beispielsweise:

```toml
[project]
name = "cara-agent-plugin"
dependencies = ["agent-plugin-api"]

[project.entry-points."cara.agent_plugins"]
cara = "cara_agent_plugin:plugin"
```

Das exportierte Objekt ist eine kleine Factory:

```python
from collections.abc import Mapping
from typing import Any

from agent_plugin_api import AgentPlugin, AgentPluginContext, AgentRunner


class CaraAgentPlugin:
    api_version = 1

    def create(
        self,
        config: Mapping[str, Any],
        context: AgentPluginContext,
    ) -> AgentRunner:
        return CaraAgentRunner(config, sessions=context.sessions)


plugin: AgentPlugin = CaraAgentPlugin()
```

## Gateway-Konfiguration

Die Auswahl sollte über normale Pydantic-Settings erfolgen. Geheimnisse bleiben
in Umgebungsvariablen und werden nicht als beliebige Plugin-Konfiguration
geloggt.

```toml
# gateway.toml
[agent]
plugin = "cara"

[agent.config]
model = "codex-spark"
workspace_root = "~/.cara/workspace"
sandbox_file = "sandbox.yml"
```

Alternativ bzw. für Deployment:

```text
CARA_AGENT_PLUGIN=cara
CARA_AGENT_CONFIG={"model":"codex-spark"}
OPENAI_API_KEY=...
```

Der Gateway-Start schlägt früh und verständlich fehl, wenn kein Plugin mit dem
konfigurierten Namen installiert ist, der Name mehrfach vorkommt oder die
Plugin-Konfiguration ungültig ist. Ein stiller Fallback auf einen anderen
Agenten wäre gefährlich und sollte nicht stattfinden.
Der Loader prüft außerdem `api_version`, damit ein inkompatibles Plugin bereits
beim Start statt mitten in einem Turn abgewiesen wird.

## Loader und DI-Anbindung

Der Loader verwendet `importlib.metadata.entry_points()` und gibt ein geprüftes
`AgentPlugin` zurück. Nur der Gateway-Composition-Root kennt Loader und Dishka:

```python
def load_agent_plugin(name: str) -> AgentPlugin:
    matches = tuple(
        entry_point
        for entry_point in entry_points(group="cara.agent_plugins")
        if entry_point.name == name
    )
    if len(matches) != 1:
        raise AgentPluginLoadError(name, len(matches))
    plugin = matches[0].load()
    return validate_plugin(plugin)
```

`create_container()` lädt das konfigurierte Plugin und registriert dessen
`AgentRunner` anstelle des fest verdrahteten `RuntimeAgentRunner`. Beim
Herunterfahren ruft der Provider `runner.close()` auf. So kann das Plugin
HTTP-Clients, Sandbox-Prozesse und Modell-Ressourcen sauber freigeben, ohne das
Gateway-Lifespan-Modul zu kennen.

## Adapter für den vorhandenen Cara-Agenten

`CaraAgentRunner` ist Bestandteil des Plugin-Pakets und übernimmt drei Aufgaben:

1. Mit `session.id` und `input_id` den früheren Kontext beim `SessionReader`
   laden und daraus den Agent-Kontext aufbauen bzw. fortsetzen.
2. Den aktuellen Text mit `Agent.start_turn()` ausführen.
3. Die internen Agent-Ereignisse vollständig in Gateway-`AgentEvent`s übersetzen.

Pro Session dauerhaft nur ein `Agent`-Objekt in einem Dictionary zu halten wäre
zwar einfach, verliert aber nach einem Gateway-Neustart den Kontext. Bevorzugt
bleibt deshalb die persistierte Gateway-Session als Source of Truth. Optional darf
das Plugin fertig aufgebaute Session-Runtimes cachen; der Cache muss aus der
Session über den Reader rekonstruierbar bleiben und begrenzt werden.

Für eine verlustfreie Übersetzung sollte das interne Agent-Ereignismodell um
folgende Informationen erweitert werden:

```text
ToolStarted:   call_id, name, arguments
ToolCompleted: call_id, name, result, is_error
TurnCompleted: kompletter Antworttext, finish_reason
```

Damit kann der Adapter dieselben IDs vom Modell bis zur Gateway-Persistenz
durchreichen. `ChatCompleted.text` ist die Summe der zuvor gestreamten Deltas.
Abbruch funktioniert über Task-Cancellation: Schließt bzw. cancelt das Gateway
den Async-Iterator, beendet der Adapter den laufenden Agent-Turn und räumt dessen
Tools auf.

## Verantwortungsgrenzen

| Gateway | Plugin |
| --- | --- |
| Channel auf Session auflösen | Modell-, Prompt-, Skill- und Tool-Aufbau |
| Session erstellen und Transcript besitzen | Kontext read-only über `SessionReader` laden |
| genau ein aktiver Turn pro Session | Ausführung des Agent-Loops |
| Gateway-Sequenznummern und WebSocket-Events | Streaming fachlicher `AgentEvent`s |
| Persistieren von Nachrichten und Tool Calls | Freigeben eigener Ressourcen |
| Cancel/Fehler in Terminal-Events übersetzen | Fehler unverfälscht propagieren |

Das Plugin erhält keine Repository-Instanz und keine Schreib-Schnittstelle.
Dadurch bleiben Transaktionen und Datenmodell unter Kontrolle des Gateways, und
ein Plugin kann nicht unbemerkt die Session-Persistenz umgehen.

## Umsetzungsplan

### Phase 1: Session-Grenze sauberziehen

- `ChannelRef` als echtes Session-Feld ergänzen.
- `session.open(channel)` hinzufügen oder zunächst `session.create(channel)`
  erweitern; ausschließlich das Gateway vergibt die Session-UUID.
- Jede User-Nachricht bekommt bereits eine eigene `input_id`; zusätzlich wird
  eine `turn_id` erzeugt.
- Einen read-only `AgentSessionReader.context_for_turn()` implementieren.

**Ergebnis:** Clients schicken nur Channel/Session-ID und neue Nachrichten. Das
Gateway ist eindeutig Owner der History.

### Phase 2: Plugin-Vertrag einführen

- `AgentSessionRef`, `AgentRunRequest`, `AgentPluginContext`, `AgentRunner` und
  `AgentPlugin` als kleine öffentliche API definieren.
- `ConversationService` ruft den Runner mit Session-Referenz, IDs und neuem Text
  auf; es übergibt keine History.
- Den alten `RuntimeAgentRunner` entfernen statt einen Kompatibilitätsadapter zu
  behalten.

**Ergebnis:** Ein Agent kann eingebunden werden, ohne Gateway-Quellcode zu
ändern.

### Phase 3: Plugin laden und sauber schließen

- Entry-Point-Loader, `AgentPluginSettings` und verständliche Startfehler bauen.
- Den statischen `_AgentProvider` durch den konfigurierten Plugin-Provider
  ersetzen.
- Beim Shutdown `runner.close()` ausführen.

**Ergebnis:** Installation plus Konfiguration aktiviert das Plugin; Ressourcen
werden korrekt geöffnet und geschlossen.

### Phase 4: Bestehenden Agenten adaptieren

- `CaraAgentRunner` lädt den Kontext über `AgentSessionReader`.
- Das interne Agent-Ereignismodell um Call-ID, Argumente, Ergebnis und Fehler
  ergänzen.
- Die vollständige Event-Übersetzung sowie Cancellation implementieren.

**Ergebnis:** Der heutige Cara-Agent läuft als erstes echtes Gateway-Plugin.

### Phase 5: Voice wirklich über das Gateway führen

- Eine `voice.llm.AgentSession`-Implementierung auf Basis von `gateway_client`
  ergänzen.
- Voice öffnet seine Gateway-Session einmal und sendet danach nur Turns mit der
  erhaltenen `session_id`.
- Der direkte lokale `Agent` bleibt höchstens ein expliziter Entwicklungsmodus.

**Ergebnis:** Voice, CLI und spätere Channels verwenden denselben Session- und
Agent-Lifecycle im Gateway.

Mindestens getestet werden sollten Channel-Normalisierung, idempotentes
Session-Öffnen, Zugriffsschutz zwischen Sessions, Plugin-Auswahl,
unbekannte/duplizierte Entry Points, ungültige Konfiguration, Kontextladen ohne
doppelte aktuelle Eingabe, Event-Mapping, Turn-Cancellation, Plugin-Fehler sowie
Resource-Cleanup beim Gateway-Shutdown.

## Bewusste Nicht-Ziele für Version 1

- Plugins dürfen keine eigenen Gateway-Routen oder Dishka-Provider registrieren.
- Kein Hot-Reload oder Wechsel des Plugins während laufender Sessions.
- Keine parallele Auswahl mehrerer Agenten pro Session.
- Keine Kompatibilitäts-Aliasse für den alten `AgentRunner`; die Signatur wird im
  gesamten Codebestand vollständig auf `AgentRunRequest` umgestellt.
