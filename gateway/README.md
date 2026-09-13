# gateway-server

Central architectural piece of Cara: a FastAPI process owning the single
long-lived JSON-RPC 2.0 WebSocket protocol, all session/turn state and
persistence, event fan-out to subscribed clients, and a pluggable agent
runtime loaded via Python entry points. [`voice`](../clients/voice) and
[`cli`](../clients/cli) are just JSON-RPC clients of this process — neither talks
to an LLM directly.

Also home to [`plugin_api`](plugin_api#readme) (`agent-plugin-api`), the
independently installable, dependency-free contract between this server and
agent plugins.

```text
Voice / CLI client --JSON-RPC/WS--> gateway --> ConversationService
    --> configured AgentRunner plugin (entry point) --> agent, models, tools
```

## Running

```powershell
$env:CARA_GATEWAY_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
```

```bash
uv run cara-gateway          # applies migrations, serves on 127.0.0.1:8000
uv run gateway-migrate         # migrations standalone
uv run cara-gateway-schema      # regenerate gateway/schema/*.json
uv run cara-gateway-client-generate gateway/schema/gateway.openrpc.json  # regenerate gateway_client
```

`CARA_GATEWAY_TOKEN` (>=32 chars) is required for the `/v1/gateway` WebSocket
handshake; health/readiness stay unauthenticated. See the [repo root
README](../README.md#run) for the full startup sequence.

## Architecture

Feature-sliced: each vertical slice under `features/` owns its own
application/domain/infrastructure/presentation layers and exposes one
`Feature` (routers, DI providers, RPC module).

```text
gateway/src/gateway/
├── app.py, container.py, lifespan.py, main.py    composition root, startup/shutdown, uvicorn entry
├── presentation/       rpc/ (channel, contract, schema export, client codegen), websocket/ (the /v1/gateway route)
├── features/            health/, automation/, conversation/ (feature-owned RPC methods and events)
├── infrastructure/      SQLModel ORM, generic Repository, Alembic runner, Scheduler wiring
└── agent_plugins/        entry-point discovery, loading, validation, DI wiring for the AgentRunner
```

## RPC surface

Each feature owns its RPC methods under `features/<name>/presentation/rpc/`.
Free functions registered on `RpcModule` delegate to the feature's service
handlers through `Inject`. Conversation also owns its subscription and event
definitions. `presentation/rpc/channels/gateway.py` composes the modules into
one `RpcChannel`; that same channel serves requests and produces the contract.

`cara-gateway-schema` exports `gateway.openrpc.json`.
`cara-gateway-client-generate` regenerates
[`gateway-client`](../generated/gateway_client#readme) from it. Both
artifacts should be updated together.
The WebSocket uses JSON-RPC 2.0; `session.event` carries server notifications.
Subscriptions are in-memory per process.

## Agent plugins

One active `AgentRunner` per process, discovered via the `cara.agent_plugins`
entry-point group and driven only through the
[`agent_plugin_api`](plugin_api) contract. Resolved once at startup
(`lifespan.py`) so a misconfigured plugin fails fast, not mid-turn. Selected
and configured via `gateway.yaml`'s `agent.plugin` / `agent.config`. The
bundled `echo` plugin (word-by-word echo) exercises the protocol without a
real model; [`agent`](../agent) is Cara's real plugin, entry point `cara`.

## Session/turn lifecycle

`ConversationService` is the sole owner of session and turn state:
`create_session`, `open_session` (find-or-create per channel, under a
process-wide lock — this is what gives clients "resume my last conversation"
behavior), `start_turn` (atomic claim, raises on a turn already running),
`cancel_turn`. Turn execution persists and republishes every `AgentEvent` as
a sequenced `GatewayEvent`.

## Persistence

SQLModel over SQLite (`aiosqlite`), migrated with Alembic. Persisted domain:
sessions, user/assistant messages, tool call sequences — not a raw chat
"runs" table.

## Configuration

`GatewaySettings` (`pydantic-settings`): init args, env (`CARA_`-prefixed),
`.env`, then `gateway.yaml`/`gateway.yml` — the repo root's `gateway.yaml` is
the single source of truth for plugin selection and everything the plugin
needs (models, workspace, sandbox). `DATABASE_URL` overrides the default
local SQLite file.

## Dependencies

- [`agent_plugin_api`](plugin_api) — the plugin loading contract.
- [`scheduler`](../libs/scheduler) — periodic housekeeping jobs.
- `cara-gateway-client-generate` (`presentation/rpc/client_codegen.py`) reads
  this package's exported OpenRPC schema to regenerate
  [`gateway-client`](../generated/gateway_client).
- Drives [`agent`](../agent) as its production plugin; consumed by
  [`voice`](../clients/voice) and [`cli`](../clients/cli) as JSON-RPC clients.
