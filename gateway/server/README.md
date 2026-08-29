# gateway-server

Central architectural piece of Cara: a FastAPI process owning the single
long-lived JSON-RPC 2.0 WebSocket protocol, all session/turn state and
persistence, event fan-out to subscribed clients, and a pluggable agent
runtime loaded via Python entry points. [`voice`](../../voice) and
[`cli`](../../cli) are just JSON-RPC clients of this process — neither talks
to an LLM directly.

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
uv run cara-gateway-schema      # regenerate gateway/server/schema/*.json
```

`CARA_GATEWAY_TOKEN` (>=32 chars) is required for the `/v1/gateway` WebSocket
handshake; health/readiness stay unauthenticated. See the [repo root
README](../../README.md#run) for the full startup sequence.

## Architecture

Feature-sliced: each vertical slice under `features/` owns its own
application/domain/infrastructure/presentation layers and exposes one
`Feature` (routers, DI providers, RPC protocol).

```text
gateway/server/src/gateway/
├── app.py, container.py, lifespan.py, main.py    composition root, startup/shutdown, uvicorn entry
├── presentation/       rpc/ (method+event registry, dispatch, schema export), websocket/ (the /v1/gateway route)
├── features/            health/, conversation/ (sessions, turns, messages, tool calls)
├── infrastructure/      SQLModel ORM, generic Repository, Alembic runner, Scheduler wiring
└── agent_plugins/        entry-point discovery, loading, validation, DI wiring for the AgentRunner
```

## RPC surface

Generated from code via `pyrpckit`, not maintained as a parallel spec — a
handler declares methods with `@method(...)`, event models with
`@event`, grouped into a `Feature.protocol`; `RpcServer` asserts at
startup that handlers match the declared protocol exactly.
`cara-gateway-schema` exports `gateway.schema.json` and
`gateway.openrpc.json`, which feed [`gateway-codegen`](../codegen) —
regenerating the schema and the client are always one change, never
independent edits.

WebSocket framing is strict JSON-RPC 2.0 (`session.event` is the notification
method for server-pushed events). Subscriptions are per-process, in-memory
(`subscription.subscribe`/`unsubscribe`) — no fan-out across multiple gateway
instances.

## Agent plugins

One active `AgentRunner` per process, discovered via the `cara.agent_plugins`
entry-point group and driven only through the
[`agent_plugin_api`](../plugin_api) contract. Resolved once at startup
(`lifespan.py`) so a misconfigured plugin fails fast, not mid-turn. Selected
and configured via `gateway.yaml`'s `agent.plugin` / `agent.config`. The
bundled `echo` plugin (word-by-word echo) exercises the protocol without a
real model; [`agent`](../../agent) is Cara's real plugin, entry point `cara`.

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

- [`agent_plugin_api`](../plugin_api) — the plugin loading contract.
- [`scheduler`](../../libs/scheduler) — periodic housekeeping jobs.
- [`gateway-codegen`](../codegen) reads this package's exported OpenRPC
  schema to regenerate [`gateway-client`](../client).
- Drives [`agent`](../../agent) as its production plugin; consumed by
  [`voice`](../../voice) and [`cli`](../../cli) as JSON-RPC clients.
