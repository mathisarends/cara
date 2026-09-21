# Traces in Jaeger ansehen

Der Compose-Stack startet Jaeger mit. Das Gateway exportiert seine Spans per
OTLP dorthin:

```powershell
docker compose up --build -d
```

Die Oberfläche liegt unter <http://localhost:16686>. Dort den Service
`cara-gateway` wählen und suchen. Spans entstehen zurzeit automatisch für
HTTP- und WebSocket-Requests (FastAPI), SQL-Statements (SQLAlchemy), MCP-Calls
(MCP-SDK) und ausgehende Requests über `httpx` und `httpx2`. Beide brauchen
einen eigenen Instrumentor: `httpx2` ist ein separates Paket, über das die
Calls zum sandbox-manager und zu cara-tools laufen, während das Deepgram-SDK
`httpx` benutzt.

Die Traces liegen nur im Speicher und sind nach einem Neustart des
`jaeger`-Containers weg.

## Konfiguration

| Variable | Default | Bedeutung |
|---|---|---|
| `CARA_TELEMETRY_ENABLED` | `false` (Compose: `true`) | Ohne diese Variable ist die OTel-API ein No-Op. |
| `CARA_TELEMETRY_SERVICE_NAME` | `cara-gateway` | Service in der Jaeger-Suche. |
| `CARA_TELEMETRY_OTLP_ENDPOINT` | `http://localhost:4317` | OTLP-gRPC-Collector. |
| `CARA_TELEMETRY_SAMPLE_RATIO` | `1.0` | Anteil der behaltenen Root-Traces. |

Für das Gateway auf dem Host reicht Jaeger allein:

```powershell
docker compose up -d jaeger
$env:CARA_TELEMETRY_ENABLED = "true"
uv run --package gateway-server cara-gateway
```

`CARA_TELEMETRY_ENABLED=false` schaltet den Export wieder ab; das Gateway läuft
dann ohne SDK und ohne Instrumentierung.

## Grenzen des aktuellen Stands

- sandbox-manager und cara-tools sind selbst nicht instrumentiert. Der
  `traceparent`-Header geht zwar raus, die Traces enden aber trotzdem am
  Client-Span.
- Der WebSocket unter `/v1/gateway` bekommt einen Span über die gesamte
  Verbindungsdauer. Als Parent für einzelne Turns ist er unbrauchbar.
- Eigene Spans für Turn, LLM-Runden, Tool-Calls und die Voice-Pipeline gibt es
  noch nicht; bisher wird nur auto-instrumentiert.
