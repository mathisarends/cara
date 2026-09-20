# Telemetry: Latenz-Tracing mit OpenTelemetry

## Ziel

Für jeden Conversation-Turn (Text oder Voice) soll ein einzelner Trace zeigen,
**wo die Zeit hingeht**. Konkret soll pro Turn beantwortbar sein:

| Frage | Span / Attribut |
|---|---|
| Wie lange dauert der ganze Turn? | `conversation.turn` |
| Wie lange warten wir auf das LLM, wie lange bis zum ersten Token? | `chat {model}` + Event `first_token` |
| Wie viele LLM-Runden (Tool-Loop) hat der Turn gebraucht? | Anzahl `chat`-Spans, `cara.agent.rounds` |
| Welches Tool ist langsam? | `execute_tool {name}` |
| Ist es die Sandbox (Netzwerk vs. Container-Exec)? | `sandbox.exec` → HTTP-Client-Span → Server-Span im sandbox-manager |
| MCP-Tools (cara-tools: Wetter, Suche)? | `mcp.call_tool {name}` → HTTP-Span |
| Wie viel kostet die Persistenz zwischen den Events? | `session.save`, `turn_lease.*`, SQLAlchemy-Spans |
| Voice: STT → LLM → TTS, wann kommt das erste Audio? | `voice.turn`, `voice.stt`, `voice.tts`, Event `first_audio` |

Nicht-Ziele (erstmal): Logs über OTel exportieren, Alerting, Tracing im Voice-Client.

## Ziel-Trace

So soll ein Voice-Turn mit einem Shell-Tool-Call im Trace-Viewer aussehen:

```
voice.turn                                         ████████████████████████████ 4.2s
├─ voice.stt                                       ███                          0.6s
├─ conversation.turn                                  ████████████████████████  3.5s
│  ├─ turn_lease.acquire                              ▏                          3ms
│  ├─ session.save  (user message)                    ▏                          8ms
│  ├─ agent.prepare_context                           ▏                         12ms
│  ├─ chat gpt-5 (round 1)                            ██████                    1.1s   first_token @ 0.7s
│  ├─ execute_tool shell                                    ███                 0.5s
│  │  ├─ session.save (tool started)                        ▏                   6ms
│  │  └─ sandbox.exec                                       ██                  0.45s
│  │     └─ POST /sandboxes/{id}/exec (httpx)               ██                  0.44s
│  │        └─ POST /sandboxes/{id}/exec (sandbox-manager)  ██                  0.43s
│  ├─ chat gpt-5 (round 2)                                     ██████████       1.8s   first_token @ 0.9s
│  └─ session.save (assistant message)                                   ▏      9ms
└─ voice.tts                                                   ███████████      1.9s   first_audio @ 0.3s
```

Die Lücke zwischen Spans ist genauso aufschlussreich wie die Spans selbst: Zeit, die in
keinem Kind-Span steckt, ist Overhead im Parent (Event-Publishing, Queue-Wartezeit, …).

## Architekturregeln (DDD)

Tracing ist ein Cross-Cutting-Concern. Die Schichtung bleibt so:

| Schicht | Darf | Darf nicht |
|---|---|---|
| `domain/` | nichts OTel-bezogenes | `opentelemetry` importieren |
| `application/` | Spans an **Use-Case-Grenzen** über die OTel-**API** (`opentelemetry.trace`) | SDK/Exporter kennen, Settings lesen |
| `infrastructure/` | Spans um Adapter (Repository, STT/TTS, Sandbox, MCP, LLM) | – |
| `platform/observability/` | SDK, Exporter, Resource, Auto-Instrumentierung konfigurieren | – |
| `agent/`, `libs/llm` | Spans über die OTel-API (Library-Regel: nur `opentelemetry-api`) | SDK konfigurieren |

Begründung, warum **kein eigener `Tracer`-Port (ABC)**: Die OTel-API ist bereits eine
herstellerneutrale Abstraktion und ohne konfiguriertes SDK ein No-Op. Ein eigener Port
würde sie nur 1:1 spiegeln. Die Domain bleibt trotzdem sauber, weil dort nie getraced wird –
Aggregate-Methoden (`Session.add_tool_call` etc.) sind reine In-Memory-Operationen im
Mikrosekundenbereich und keine Latenzquelle.

Domain-Events (`ConversationEventType.*`) werden **nicht** zu Spans. Sie bleiben das, was
sie sind; Spans messen Arbeit, Events beschreiben Fakten. Wo nötig, wird ein Zeitpunkt als
Span-Event (`span.add_event("first_token")`) markiert.

## Konventionen

- **Tracer-Namen** = Modulname: `tracer = trace.get_tracer(__name__)` auf Modulebene.
- **Span-Namen** niedrige Kardinalität (keine IDs im Namen): `conversation.turn`,
  `execute_tool shell`, `chat gpt-5`.
- **Eigene Attribute** mit Präfix `cara.`:
  `cara.session.id`, `cara.channel`, `cara.turn.trigger` (`user` | `scheduled` | `voice`),
  `cara.voice.turn.id`, `cara.agent.rounds`, `cara.tool.is_error`.
- **GenAI-Attribute** nach OTel-Semconv: `gen_ai.operation.name`, `gen_ai.request.model`,
  `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.tool.name`,
  `gen_ai.tool.call.id`.
- **Keine Inhalte** in Attributen: keine User-Nachrichten, keine Tool-Argumente, keine
  Tool-Outputs, keine Transkripte. Längen sind okay (`cara.input.chars`).
- Fehler: `span.record_exception(error)` + `span.set_status(StatusCode.ERROR)`. Erwartete
  Tool-Fehler (`ToolFailure`) setzen nur `cara.tool.is_error=true`, keinen ERROR-Status.
- **Keine Spans über `yield` in async Generatoren halten** (`with start_as_current_span`
  um ein `yield` herum führt zu Context-Detach-Fehlern, sobald der Consumer zwischen den
  Iterationen woanders weiterläuft). Spans immer im **Konsumenten** um das `async for`
  legen – siehe `TurnWorker._execute` und `Agent._stream_completion`.

## Context-Propagation (warum es fast von selbst funktioniert)

OTel speichert den aktiven Span in einer `contextvar`. `asyncio.create_task` kopiert den
aktuellen Context. Daraus folgt für den bestehenden Code:

- `VoiceTurnService.final_transcript` → `TurnWorker.start` → `start_committed` →
  `asyncio.create_task(self._execute(...))`: Wenn `final_transcript` in einem aktiven
  `voice.turn`-Span läuft, wird `conversation.turn` automatisch dessen Kind.
- `Agent.start_turn` → `asyncio.create_task(self._run_turn(...))`: wird innerhalb von
  `conversation.turn` aufgerufen, also hängen alle `chat`/`execute_tool`-Spans darunter.
- `httpx`-Instrumentierung injiziert `traceparent`-Header → sandbox-manager und cara-tools
  (MCP über HTTP) setzen den Trace fort, sobald sie selbst instrumentiert sind.

Ausnahme: `_conversation_to_speech` / `_synthesize` werden **vor** dem Turn per
`_start_task` gestartet und hören über den Event-Bus mit. Sie laufen im Context von
`voice.turn` (gut), aber nicht unterhalb von `conversation.turn` (auch richtig – TTS ist
ein Geschwister, kein Kind).

---

## Implementierungsskizzen

Die Phasen sind unabhängig mergebar. Phase 1 zuerst; danach liefert jede Phase für sich
Erkenntnisse.

### Phase 1 – SDK-Setup, Exporter, Auto-Instrumentierung

**Abhängigkeiten**

- `gateway/pyproject.toml`:
  `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-grpc`,
  `opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-httpx`,
  `opentelemetry-instrumentation-sqlalchemy`
- `agent/pyproject.toml`, `libs/llm/pyproject.toml`: nur `opentelemetry-api`
- `sandbox_manager/pyproject.toml`, `cara-tools/pyproject.toml`: wie Gateway (Phase 6)

**Settings** – `gateway/src/gateway/platform/observability/settings.py`

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelemetrySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CARA_TELEMETRY_")

    enabled: bool = False
    service_name: str = "cara-gateway"
    otlp_endpoint: str = "http://localhost:4317"
    # 1.0 im Homelab; ein Turn ist selten genug, um alles zu behalten.
    sample_ratio: float = 1.0
```

**Setup** – `gateway/src/gateway/platform/observability/telemetry.py`

```python
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from sqlalchemy.ext.asyncio import AsyncEngine

from gateway.platform.observability.settings import TelemetrySettings


class Telemetry:
    """Owns the tracer provider for the lifetime of the app."""

    def __init__(self, settings: TelemetrySettings) -> None:
        self._settings = settings
        self._provider: TracerProvider | None = None

    def install(self, app: FastAPI) -> None:
        if not self._settings.enabled:
            return
        provider = TracerProvider(
            resource=Resource.create({SERVICE_NAME: self._settings.service_name}),
            sampler=ParentBased(TraceIdRatioBased(self._settings.sample_ratio)),
        )
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=self._settings.otlp_endpoint))
        )
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app, excluded_urls="/health")
        HTTPXClientInstrumentor().instrument()
        self._provider = provider

    def instrument_engine(self, engine: AsyncEngine) -> None:
        if self._provider is not None:
            SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)

    def shutdown(self) -> None:
        if self._provider is not None:
            self._provider.shutdown()
```

**Wiring**

- `app.py` / `create_app()`: `Telemetry(TelemetrySettings())` erzeugen und
  `telemetry.install(app)` aufrufen, **bevor** Middleware/Router registriert werden,
  damit der FastAPI-Server-Span der äußerste ist. Instanz in `app.state.telemetry` ablegen.
- `platform/database/di.py` → `DatabaseProvider.engine`: nach Engine-Erzeugung
  `telemetry.instrument_engine(engine)`. (Telemetry dafür als `APP`-scoped Dependency
  im `DatabaseProvider` bzw. einem neuen `ObservabilityProvider` bereitstellen.)
- `lifespan.py`: im äußersten `finally` `telemetry.shutdown()` (flusht den Batch-Processor).
- `RequestLoggingMiddleware` bleibt – Logs und Traces ergänzen sich. Optional in einem
  Folgeschritt die `trace_id` ins Log-Format aufnehmen
  (`opentelemetry-instrumentation-logging`, `%(otelTraceID)s`).
- `platform/observability/__init__.py`: nur `Telemetry` und `TelemetrySettings`
  re-exportieren, falls von außerhalb gebraucht (siehe CLAUDE.md – restriktiv).

**Achtung WebSocket**: Die FastAPI-Instrumentierung erzeugt für `/v1/gateway` einen Span
über die **gesamte Verbindungsdauer**. Der ist als Parent für Turns unbrauchbar (Minuten
bis Stunden lang). Darum starten `conversation.turn` und `voice.turn` in Phase 2/5 einen
**neuen Root-Trace** mit einem Link auf den aktuellen Span (siehe `_turn_context`), statt
Kind des WS-Spans zu werden.

**Backend** – `compose.yml` ergänzen:

```yaml
  jaeger:
    image: jaegertracing/jaeger:latest
    ports:
      - "16686:16686"   # UI
      - "4317:4317"     # OTLP gRPC
    profiles: ["observability"]
```

Gateway-Service: `CARA_TELEMETRY_ENABLED=true`,
`CARA_TELEMETRY_OTLP_ENDPOINT=http://jaeger:4317`.
Start: `docker compose --profile observability up`. UI: http://localhost:16686.

**Fertig, wenn**: Ein REST-Call (`GET /v1/sessions`) erscheint in Jaeger mit
SQLAlchemy-Kind-Spans.

### Phase 2 – Turn-Span im `TurnWorker`

Datei: `gateway/src/gateway/features/conversation/application/turn_worker.py`

```python
from opentelemetry import trace
from opentelemetry.trace import Link, StatusCode

tracer = trace.get_tracer(__name__)


class TurnWorker:
    async def _execute(self, session_id, text, *, persist_input, input_id=None):
        with tracer.start_as_current_span(
            "conversation.turn",
            context=_turn_context(),
            links=_current_link(),
            attributes={
                "cara.session.id": str(session_id),
                "cara.turn.trigger": "user" if input_id else "scheduled",
                "cara.input.chars": len(text),
            },
        ) as span:
            ...  # bestehender Body unverändert
            # im except CancelledError:
            span.set_attribute("cara.turn.outcome", "cancelled")
            # im except Exception:
            span.record_exception(error)
            span.set_status(StatusCode.ERROR, error_message)
```

Außerdem kleine Spans um die DB-Schritte, die im Hot Path liegen:

```python
    async def _acquire_lease(self, session_id: UUID) -> bool:
        with tracer.start_as_current_span("turn_lease.acquire"):
            async with self._leases() as lease:
                return await lease.acquire(session_id)
```

(analog `turn_lease.release`, `session.load` in `_get`, `session.save` in `_save`)

Helper (privat, unten im Modul – Stepdown-Regel):

```python
def _turn_context() -> Context | None:
    """Start a fresh trace unless we are already inside a voice turn."""
    current = trace.get_current_span()
    if _is_long_lived(current):
        return Context()  # neuer Root
    return None  # aktuellen Context als Parent nutzen


def _current_link() -> list[Link]:
    current = trace.get_current_span().get_span_context()
    return [Link(current)] if current.is_valid else []
```

`_is_long_lived` erkennt den WebSocket-Server-Span (z. B. über ein Context-Flag, das
die RPC-Presentation-Schicht setzt, oder simpler: `TurnWorker.start` wird von der
RPC-Methode *immer* mit neuem Root gestartet und `VoiceTurnService` setzt vorher seinen
`voice.turn`-Span). **Empfehlung**: einfachste Variante zuerst – in
`gateway/src/gateway/presentation/websocket/` pro eingehendem RPC-Request einen eigenen
Root-Span `rpc {method}` (mit Link auf den WS-Span) starten. Dann ist der Turn-Span
automatisch Kind eines kurzen RPC-Spans und `_turn_context()` entfällt.

Datei: `gateway/src/gateway/features/conversation/application/turn_execution.py`

```python
    async def _save_session(self) -> None:
        with tracer.start_as_current_span("session.save"):
            async with self._sessions() as sessions:
                self._session = await sessions.save(self._session)
```

**Warum das wichtig ist**: `TurnExecution.handle` speichert die komplette Session bei
**jedem** `ToolCallStarted`, `ToolCallCompleted`, `TurnSteered` und `ChatCompleted` –
synchron im Streaming-Pfad, bevor das Event publiziert wird. `SQLSessionRepository.save`
mappt die ganze Session inkl. aller Einträge (`_to_orm`). Mit wachsender Session-Länge
wird das linear teurer. Das ist ein Hauptverdächtiger und sollte nach dieser Phase
sichtbar sein (Attribut `cara.session.entries` am `session.save`-Span setzen).

**Fertig, wenn**: Ein Text-Turn über die CLI erzeugt einen Trace mit
`conversation.turn` → `session.save`/`turn_lease.*` → SQL-Spans.

### Phase 3 – Agent-Loop: LLM-Runden und Tool-Calls

Datei: `agent/src/agent/agent.py` (nur `opentelemetry-api`)

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)


class Agent:
    async def _run_loop(self, events: _EventQueue) -> None:
        rounds = 0
        ...
        while True:
            rounds += 1
            trace.get_current_span().set_attribute("cara.agent.rounds", rounds)
            end = await self._stream_completion(events)
            ...

    async def _stream_completion(self, events: _EventQueue) -> ModelResponse:
        with tracer.start_as_current_span(
            f"chat {self._model.name}",
            attributes={
                "gen_ai.operation.name": "chat",
                "gen_ai.request.model": self._model.name,
                "cara.context.messages": len(self._context),
            },
        ) as span:
            end = None
            first_token = True
            async for event in self._model.stream(...):
                match event:
                    case ModelTextDelta(delta=delta) if delta:
                        if first_token:
                            span.add_event("first_token")
                            first_token = False
                        await events.put(TextDelta(delta))
                    case ModelResponse():
                        end = event
            if end is None:
                raise ModelError(...)
            span.set_attribute("gen_ai.response.finish_reasons", [end.finish_reason])
            span.set_attribute("cara.tool_calls", len(end.tool_calls))
            # sobald ModelResponse Usage liefert:
            # span.set_attribute("gen_ai.usage.input_tokens", end.usage.input_tokens)
            return end

    async def _execute_tool(self, name, arguments) -> object:
        with tracer.start_as_current_span(
            f"execute_tool {name}",
            attributes={
                "gen_ai.operation.name": "execute_tool",
                "gen_ai.tool.name": name,
            },
        ) as span:
            try:
                result = await self._tools.execute(name, arguments)
            except FatalToolError as error:
                span.record_exception(error)
                span.set_status(StatusCode.ERROR)
                raise
            except Exception as error:
                result = ToolFailure(_error_content(error))
            span.set_attribute("cara.tool.is_error", isinstance(result, ToolFailure))
            return result
```

Hinweise:

- `self._model.name` existiert evtl. nicht – `ChatModel` (in `libs/llm/ports.py`) ggf.
  um eine abstrakte Property `name` erweitern, statt per `getattr` zu proben.
- Die „Wartezeit bis `first_token`“ ist die eigentliche LLM-Latenz (Queue + Prefill).
  Die Zeit danach ist Generierung. Beides getrennt zu sehen ist der Hauptgewinn.
- Falls Tool-Aufrufe später parallel laufen (`asyncio.gather`), funktionieren die Spans
  unverändert, weil jede Task den Context erbt.
- `ToolResultMiddleware` misst schon Dauer für Logs; die Log-Zeilen bleiben, sie werden
  über die `trace_id` im Log-Format mit dem Trace verknüpfbar.
- **pydantic-ai** hat eigene OTel-Instrumentierung (`instrument=True` am Model). Nicht
  zusätzlich aktivieren, sonst doppelte `chat`-Spans. Optional später: statt des eigenen
  Spans in `_stream_completion` pydantic-ai-Instrumentierung in `libs/llm/codex.py`
  nutzen, falls dort Token-Usage sauberer ankommt.

Datei: `gateway/src/gateway/features/conversation/infrastructure/cara_runtime.py`

```python
    async def _get_or_create_agent(self, session, *, input_id=None) -> Agent:
        with tracer.start_as_current_span("agent.prepare_context") as span:
            async with self._registry_lock:
                agent = self._agents.get(session.id)
                span.set_attribute("cara.agent.cached", agent is not None)
                ...
```

Damit wird sichtbar, ob der Kontext-Aufbau aus der DB (`_context_messages`) beim ersten
Turn einer Session relevant ist – und ob `_registry_lock` Turns verschiedener Sessions
gegenseitig blockiert (Lock-Wartezeit = Span-Dauer ohne SQL-Kinder).

**Fertig, wenn**: Ein Turn mit Tool-Call zeigt `chat` → `execute_tool` → `chat`.

### Phase 4 – Sandbox und MCP

Datei: `gateway/src/gateway/agent_runtime/sandbox.py`

```python
    async def execute(self, command, *, cwd=None, env=None, stdin=None, timeout=...):
        with tracer.start_as_current_span(
            "sandbox.exec",
            attributes={"cara.sandbox.timeout_s": timeout_seconds},
        ) as span:
            ...  # bestehender Body
            span.set_attribute("cara.sandbox.exit_code", result.exit_code)
            span.set_attribute("cara.sandbox.timed_out", result.timed_out)
```

Analog `sandbox.ensure` (läuft in `CaraAgentRuntime.prepare` – Cold-Start des
Containers!), `sandbox.read_file`, `sandbox.write_file`. Der Befehl selbst gehört **nicht**
ins Attribut (kann Secrets enthalten).

Der httpx-Span darunter kommt aus Phase 1 automatisch – sofern `sandbox_manager_client`
httpx verwendet (prüfen: `generated/sandbox_manager_client`). Differenz
`sandbox.exec` − HTTP-Span = Client-Overhead; HTTP-Client-Span − Server-Span (Phase 6) =
Netzwerk.

Datei: `gateway/src/gateway/agent_runtime/mcp.py` → `_remote_tool.invoke`

```python
    async def invoke(arguments: BaseModel) -> object:
        with tracer.start_as_current_span(
            f"mcp.call_tool {definition.name}",
            attributes={"cara.mcp.server": server_name},
        ):
            ...
```

### Phase 5 – Voice-Pipeline

Datei: `gateway/src/gateway/features/voice/application/voice_turn_service/service.py`

Der Voice-Turn lebt über mehrere Methodenaufrufe (`start` → `receive_media`* →
`final_transcript` → `_synthesize` → `playback_completed`). Ein einzelnes
`with`-Statement passt nicht. Darum: Span manuell starten und pro Voice-Turn halten.

```python
tracer = trace.get_tracer(__name__)


class VoiceTurnService:
    def __init__(self, ...):
        ...
        self._turn_spans: dict[UUID, Span] = {}

    async def start(self, ...) -> VoiceTurn:
        ...
        span = tracer.start_span(
            "voice.turn",
            context=Context(),  # eigener Root, nicht unter dem Media-WebSocket
            attributes={
                "cara.voice.turn.id": str(turn.id),
                "cara.voice.session.id": str(voice_session.id),
            },
        )
        self._turn_spans[turn.id] = span
        # STT-Task im Kontext des Turn-Spans starten:
        with trace.use_span(span, end_on_exit=False):
            self._start_task(turn.id, self._transcribe(turn.id, queue))

    async def final_transcript(self, voice_turn_id, text) -> VoiceTurn:
        span = self._turn_spans.get(voice_turn_id)
        with trace.use_span(span, end_on_exit=False) if span else nullcontext():
            ...  # bestehender Body: _conversation_to_speech + TurnWorker.start
                 # erben jetzt den voice.turn-Context

    async def playback_completed(self, voice_turn_id) -> VoiceTurn:
        ...
        self._end_turn_span(voice_turn_id)
    # ebenso in _fail, _cancel_turn, interrupt, discard-Pfad
```

Kind-Spans:

```python
    async def _transcribe(self, voice_turn_id, queue) -> None:
        with tracer.start_as_current_span("voice.stt") as span:
            first_partial = True
            async for update in self._speech_to_text.transcribe(_audio(queue)):
                if first_partial:
                    span.add_event("first_partial")
                    first_partial = False
                ...

    async def _synthesize(self, voice_session_id, voice_turn_id, text) -> None:
        with tracer.start_as_current_span("voice.tts") as span:
            segments_count = 0
            while (segment := await segments.next()) is not None:
                segments_count += 1
                async for chunk in self._text_to_speech.synthesize(segment):
                    if not started:
                        span.add_event("first_audio")
                        ...
            span.set_attribute("cara.tts.segments", segments_count)
```

Die wichtigste Voice-Kennzahl ist **Time-to-first-Audio** = Zeitpunkt `first_audio`
minus Ende von `voice.stt`. Sie setzt sich zusammen aus: Turn-Start (Lease, Save) +
LLM `first_token` + Satz-Segmentierung (`SpeechSegments` wartet auf Satzende!) +
TTS-Latenz bis zum ersten Chunk. Den Anteil der Segmentierung sichtbar machen:
`span.add_event("segment_ready", {"cara.tts.segment.chars": len(segment)})` vor jedem
`synthesize`-Aufruf.

**Verdacht im Hot Path**: `_synthesize` ruft `await self._find_turn(voice_turn_id)` für
**jeden Audio-Chunk** auf – jedes Mal eine DB-Transaktion. Nach Phase 1 (SQLAlchemy-Spans)
sieht man das als Kette von SELECTs unter `voice.tts`. Wenn relevant: `turn.index` einmal
vor der Schleife lesen.

Hinweis Barge-in/Interrupt: Beim Abbruch den Span mit
`cara.voice.turn.outcome = "interrupted"` beenden, nicht mit ERROR-Status.

### Phase 6 – Downstream-Services

`sandbox_manager` und `cara-tools` bekommen dasselbe Minimal-Setup wie Phase 1
(FastAPI- bzw. Starlette-Instrumentierung + OTLP-Exporter, eigener `service_name`).
Kein Code in Feature-Modulen nötig; der `traceparent`-Header aus dem Gateway verbindet
die Traces automatisch. Im sandbox-manager lohnt ein manueller Span um den eigentlichen
Container-Exec (Docker-API-Aufruf), um Container-Zeit von HTTP-Handling zu trennen.

Die Setup-Logik (`Telemetry`-Klasse) nicht in eine Shared-Lib ziehen, solange es nur
drei ~40-Zeilen-Kopien sind – erst bei Divergenz-Schmerzen.

### Phase 7 (optional) – Metriken aus Spans

Für Trends über Zeit („wird TTFT schlechter?“) statt Einzel-Traces:

- Einfachste Variante: Jaeger hat „Monitor“-Tab (SPM), braucht aber Prometheus.
- Alternative: OTel Collector mit `spanmetrics`-Connector zwischen Gateway und Jaeger;
  erzeugt Histogramme pro Span-Name (`conversation.turn`, `chat *`,
  `execute_tool *`, `voice.tts`) ohne Code-Änderung.
- Erst bei Bedarf: explizite Histogramme über die Metrics-API
  (`cara.voice.time_to_first_audio`, `gen_ai.client.operation.duration`).

### Phase 8 (optional) – Voice-Client

Echte End-to-End-Latenz beginnt bei „User hört auf zu sprechen“ (VAD im Client) und endet
bei „erster Ton aus dem Lautsprecher“. Dafür müsste der Voice-Client einen Span öffnen und
`traceparent` in die RPC-Params von `voice.turn.start` legen; der Gateway extrahiert ihn
(`TraceContextTextMapPropagator().extract(carrier)`) und nutzt ihn als Parent statt
`Context()`. Die vorhandenen `VoiceLifecycleEvent`s (`clients/voice/.../lifecycle/`) sind
dafür gute Hook-Punkte – ein `TracingObserver` neben `LifecycleTrace` würde reichen.

---

## Tests

Pro Phase ein Test mit In-Memory-Exporter, der nur die **Struktur** prüft (Span-Namen und
Parent-Beziehungen), nicht Zeiten.

`gateway/tests/conftest.py` (bzw. `agent/tests/conftest.py`):

```python
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

_EXPORTER = InMemorySpanExporter()
_provider = TracerProvider()
_provider.add_span_processor(SimpleSpanProcessor(_EXPORTER))
trace.set_tracer_provider(_provider)  # nur einmal pro Prozess erlaubt


@pytest.fixture
def spans() -> InMemorySpanExporter:
    _EXPORTER.clear()
    return _EXPORTER
```

Beispiel:

```python
async def test_tool_call_is_traced_inside_the_turn(spans, worker_with_tool_call):
    await worker_with_tool_call.run_turn()

    by_name = {span.name: span for span in spans.get_finished_spans()}
    turn = by_name["conversation.turn"]
    tool = by_name["execute_tool shell"]
    assert tool.context.trace_id == turn.context.trace_id
    assert by_name["chat fake-model"].parent.span_id == turn.context.span_id
```

`opentelemetry-sdk` nur als Dev-Dependency in `agent/`.

## Auswertung: So findet man die Latenz

1. Jaeger-UI → Service `cara-gateway` → Operation `conversation.turn` (bzw. `voice.turn`)
   → nach Dauer sortieren, langsamsten Trace öffnen.
2. Im Timeline-View die **Critical Path**-Ansicht nutzen: Sie markiert, welche Spans die
   Gesamtdauer tatsächlich bestimmen.
3. Typische Muster:
   - Langer `chat`-Span, spätes `first_token` → Provider-Latenz/Prefill (Kontext zu groß?
     `cara.context.messages` prüfen).
   - Viele `chat`-Runden → Modell ruft Tools einzeln nacheinander auf.
   - `execute_tool` ≫ `sandbox.exec` → Overhead im Tool selbst.
   - `sandbox.ensure` lang → Container-Cold-Start.
   - Viele `session.save` mit steigender Dauer → Persistenz-Kosten wachsen mit der Session.
   - Lücke zwischen `first_token` und `first_audio` → Satz-Segmentierung oder TTS.
4. Traces vergleichen (Jaeger „Compare“): schneller vs. langsamer Turn derselben Art.

## Offene Fragen

- Wie heißt das Modell zur Laufzeit (`ChatModel`-Port hat evtl. kein `name`)? →
  in Phase 3 klären und ggf. den Port erweitern.
- Liefert `ModelResponse` Token-Usage? Wenn nicht: in `libs/llm/codex.py` aus der
  pydantic-ai-Response übernehmen.
- Soll der RPC-Layer (pyrpckit) generisch pro Methode einen Span öffnen (Phase 2,
  Empfehlung) – gibt es dort einen Middleware-Hook?
- Sampling: 100 % ist im Homelab okay; bei Automations/Alarmen, die häufig laufen, ggf.
  `cara.turn.trigger=scheduled` niedriger samplen.
