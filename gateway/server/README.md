# Gateway server

`gateway` is the central architectural piece of Cara: a FastAPI process that
owns the single long-lived JSON-RPC 2.0 WebSocket protocol, all session/turn
state and persistence, event fan-out to subscribed clients, and a pluggable
agent runtime loaded via Python entry points. [`voice`](../../voice) and
[`cli`](../../cli) are just JSON-RPC clients of this process — neither talks to
an LLM directly.

```text
Voice / CLI client
       │ JSON-RPC 2.0 over WebSocket ("/v1/gateway")
       ▼
gateway: resolve channel -> session, dispatch RPC method
       │
       ▼
ConversationService (owns session, turn locking, persistence, event publish)
       │ AgentRunRequest(session, turn_id, input_id, input)
       ▼
configured AgentRunner plugin (installed package, discovered by entry point)
       │ reads prior context via AgentSessionReader (read-only)
       ▼
agent, models, tools, skills
```

## Table of contents

- [Running the gateway](#running-the-gateway)
- [Architecture](#architecture)
- [JSON-RPC / OpenRPC schema generation](#json-rpc--openrpc-schema-generation)
- [WebSocket protocol](#websocket-protocol)
- [Agent plugin system](#agent-plugin-system)
- [Session and turn lifecycle](#session-and-turn-lifecycle)
- [Persistence and migrations](#persistence-and-migrations)
- [Composition root](#composition-root)
- [Configuration](#configuration)

## Running the gateway

```bash
uv run cara-gateway          # applies pending Alembic migrations, serves on 127.0.0.1:8000
uv run gateway-migrate        # run migrations standalone
uv run cara-gateway-schema     # regenerate gateway/server/schema/*.json from the RPC registry
```

Clients connect to `ws://127.0.0.1:8000/v1/gateway`. See the [repo root
README](../../README.md#run) for the full startup sequence, including the
`scripts/start_gateway.sh` convenience wrapper.

## Architecture

Feature-sliced: each vertical slice under `features/` owns its own
`application`/`domain`/`infrastructure`/`presentation` layers and exposes one
`Feature` (name, FastAPI routers, DI providers, RPC protocol) that the app and
the RPC registry are assembled from.

```text
gateway/server/src/gateway/
├── app.py              create_app(): mounts the websocket router + every Feature's routers
├── container.py          composition root: builds the Dishka container from all providers
├── lifespan.py            startup: resolve AgentRunner (fail fast), start Scheduler; shutdown: reverse
├── main.py                 uvicorn.run("gateway.app:app", host="127.0.0.1", port=8000)
├── presentation/          protocol/transport layer shared by every feature
│   ├── rpc/                 decorator-based method/event registry, dispatch, JSON-RPC envelopes, schema export
│   └── websocket/            the /v1/gateway route and one GatewayConnection per socket
├── features/
│   ├── health/               /v1/health, /v1/readiness
│   └── conversation/          sessions, turns, messages, tool calls — the core feature
├── infrastructure/          cross-cutting: SQLModel ORM, generic Repository, Alembic runner, Scheduler wiring
└── agent_plugins/           entry-point discovery, loading, validation, DI wiring for the AgentRunner
```

## JSON-RPC / OpenRPC schema generation

The RPC surface is generated *from code*, not maintained as a parallel spec —
`rpckit` is the decorator-driven, transport-agnostic JSON-RPC
library gateway builds its interface on; `gateway.presentation.rpc` is a thin
gateway-flavored surface over it (adding `ResourceNotFoundError` and
`TurnAlreadyRunningError` for gateway's own error codes). Dispatch is checked
against the declared protocol at construction time so the two can never drift
apart.

1. **Declare a method.** A feature's RPC handler subclasses `RpcHandler` and
   decorates each method with `@rpc.method(name, summary=..., errors=(...))`.
   The single parameter and return type must be Pydantic models (or `None`);
   the decorator inspects the live type hints to build the method's schema.
   Declared errors are `RpcError` subclasses, not bare codes, so the contract
   and the implementation cannot drift:

   ```python
   @rpc.method(
       ConversationRpcMethod.SESSION_CREATE,
       summary="Create a conversation session.",
       errors=(RpcInvalidParamsError, RpcInternalError),
   )
   async def create_session(self, params: CreateSessionParams) -> SessionResponse:
       session = await self._service.create_session(_channel_ref(params), params.metadata)
       return session_response(session)
   ```

2. **Declare a notification payload.** Event models are decorated with
   `@rpc.event`, which cross-checks the model's own `type: Literal[...]`
   field and derives the event name from it.

3. **Group into a feature.** `rpc.feature(name, handlers=..., notifications=(...))`
   bundles handler classes with their notification types into one
   `RpcFeatureDefinition`, exposed as `Feature.protocol`.

4. **Merge into one protocol.** `gateway_protocol()` combines every feature's
   protocol into a single `rpckit.RpcProtocol`, raising on any name collision.

5. **Verify at startup.** `RpcServer.__init__` (via its `RpcDispatcher`)
   asserts that the live handler instances expose exactly the method names
   the protocol declares — a structural guarantee, not a convention.

6. **Export.** `cara-gateway-schema` (from
   `presentation/rpc/schema_export.py`) renders two files from the same
   registry:

   | File | Format |
   | --- | --- |
   | `gateway/server/schema/gateway.schema.json` | Plain JSON Schema: a `oneOf` over per-method request envelopes, `RpcSuccess`/`RpcFailure`, and notification wrappers, plus `x-rpc-methods`/`x-rpc-notifications`/`x-rpc-events` side-tables. |
   | `gateway/server/schema/gateway.openrpc.json` | OpenRPC 1.3.2, with the same `x-rpc-notifications`/`x-rpc-events` extensions since OpenRPC has no native notification concept. |

   ```bash
   uv run cara-gateway-schema [--output-dir DIR]   # default: gateway/server/schema/
   ```

`gateway.openrpc.json` is in turn the input to
[`gateway-codegen`](../codegen) generator — regenerating the
schema and regenerating the client are always two steps of one change, never
independent edits.

## WebSocket protocol

- **Route.** `/v1/gateway`, one Dishka-injected `GatewayConnection` per socket
  (`Scope.SESSION`). The connection loop accepts the socket, spawns a
  background task that forwards subscribed conversation events, then loops
  `receive_json()` → dispatch until disconnect.
- **Framing** is strict JSON-RPC 2.0:

  | Message | Shape |
  | --- | --- |
  | Request | `{"jsonrpc":"2.0","id":<id>,"method":"session.create","params":{...}}` |
  | Success | `{"jsonrpc":"2.0","id":<id>,"result":{...}}` |
  | Error | `{"jsonrpc":"2.0","id":<id>,"error":{"code":<int>,"message":<str>}}` |
  | Notification (server → client) | `{"jsonrpc":"2.0","method":"session.event","params":{...}}` (no `id`) |

  A request sent without an `id` is treated as fire-and-forget and never
  receives a reply.
- **Error codes** (`RpcErrorCode`) cover the standard JSON-RPC set plus
  app-specific codes, including `RESOURCE_NOT_FOUND = -32004` (unknown
  session) and `TURN_ALREADY_RUNNING = -32009` (a second turn while one is
  active). Domain exceptions are mapped to these centrally in
  `GatewayConnection`'s error handling, not scattered per handler.
- **Subscriptions.** `subscription.subscribe` / `subscription.unsubscribe` register a
  client against a session id in an in-memory `EventBroker`. Each connected
  socket owns one event queue; publishing a `GatewayEvent` only reaches
  clients subscribed to that specific session. The broker is process-local —
  it does not fan out across multiple gateway instances.
- **Session events** (`session.event` notification payload) are a
  `type`-discriminated union: `turn.started`, `chat.delta`, `chat.completed`,
  `tool_call.started`, `tool_call.completed`, `turn.completed`,
  `turn.cancelled`, `turn.failed` — each carrying `event_id`, `timestamp`,
  `session_id`, a monotonically increasing `sequence`, and `metadata`.

## Agent plugin system

The Gateway hosts exactly one active `AgentRunner` per process, discovered by
Python entry point and driven only through the contract defined in
[`agent_plugin_api`](../plugin_api) — see that package for the full
`AgentRunner`/`AgentPlugin`/`AgentSessionReader` contract.

1. **Discovery.** `load_agent_plugin(name)` looks up
   `importlib.metadata.entry_points(group="cara.agent_plugins")`, requires
   exactly one match, loads the factory, and calls it once.
2. **Validation.** The loaded `AgentPlugin` is checked against the
   `@runtime_checkable` protocol and its `api_version` compared against
   `AGENT_PLUGIN_API_VERSION`. Every failure mode — not installed, duplicate
   registration, load failure, wrong shape, version mismatch — raises
   `AgentPluginLoadError` with a specific reason.
3. **Construction.** `AgentPluginProvider` (Dishka, `Scope.APP`) reads
   `AgentPluginSettings` (`plugin: str`, `config: dict`), builds an
   `AgentPluginContext` from an injected `AgentSessionReader`, and calls
   `plugin.create(settings.config, context)`.
4. **Fail fast, not mid-turn.** `lifespan.py` resolves the `AgentRunner` once
   at startup, so a missing plugin, a name collision, or invalid
   `[agent.config]` crashes the process before it accepts any connection —
   never partway through a user's turn.
5. **Shutdown.** `runner.close()` is called on container teardown, giving the
   plugin a chance to release HTTP clients, sandbox processes, or model
   resources.

The bundled reference plugin, entry point name `echo`
(`gateway.features.conversation.infrastructure.echo_agent:create_plugin`),
streams the input back word-by-word — useful for exercising the protocol
without a real model. [`agent`](../../agent) is Cara's real plugin, registered
under the entry point name `cara` and selected via `gateway.yaml`:

```yaml
agent:
  plugin: cara
  config:
    models:
      - gpt-5.3-codex-spark
      - gpt-5.6-sol
```

## Session and turn lifecycle

`ConversationService` is the sole owner of session and turn state:

- **`create_session`** always creates a new session for a `ChannelRef`.
- **`open_session`** (`session.open`) — under a process-wide `asyncio.Lock` —
  finds the latest session for a channel or creates one. This is what gives
  [`voice`](../../voice) and [`cli`](../../cli) "resume my last conversation on
  this channel" behavior without either client tracking a session id itself.
- **`start_turn`** claims the session via an atomic
  `UPDATE ... WHERE turn_active = false`, raising `SessionBusyError` (→
  `TURN_ALREADY_RUNNING`) if a turn is already running — a guarantee that
  holds even across multiple gateway processes sharing one database, not just
  within one process. On success it spawns a background task and yields
  control (`await asyncio.sleep(0)`) only once that task has entered its
  `try/finally`, so a caller can never cancel it before cleanup is armed.
- **Turn execution** appends the user message, publishes `turn.started`,
  builds an `AgentRunRequest`, and iterates the plugin's `AgentRunner.run()`,
  persisting each `AgentEvent` as it arrives (assistant text, tool call
  start/complete) and republishing it as a sequenced `GatewayEvent` to
  subscribers. `asyncio.CancelledError` becomes `turn.cancelled`; any other
  exception becomes `turn.failed` with a code and message. Either path fails
  any still-pending tool calls before finishing. `release_turn` always runs
  in a `finally`, clearing `turn_active` regardless of outcome.
- **`cancel_turn`** cancels the tracked background task for a session and
  awaits its teardown.
- **Shutdown** cancels every outstanding turn task.

## Persistence and migrations

SQLModel over SQLite (`aiosqlite`), migrated with Alembic
(`gateway/migrations/versions/`). The persisted domain is sessions, user and
assistant messages, and tool call sequences/calls — deliberately not a raw
chat "runs" table. `gateway-migrate` (or `cara-gateway`'s own startup step)
applies pending migrations before serving traffic.

## Composition root

`container.py` builds one Dishka container from every provider:
`AgentPluginProvider`, `DatabaseProvider`, `SchedulerProvider`,
`GatewayProvider` (the per-connection WebSocket scope), each feature's own
providers, and `FastapiProvider`. This is the only place that knows about
Dishka, SQLModel, and the concrete `AgentRunner` implementation — features and
the `agent_plugin_api` contract stay decoupled from it.

The [`scheduler`](../../scheduler) package is wired in the same way
(`SchedulerProvider`), currently used for periodic housekeeping jobs; see
that package's README for its own store/runner model.

## Configuration

`GatewaySettings` (`pydantic-settings`) reads, in priority order: init
arguments, environment variables (`CARA_`-prefixed), `.env`, then
`gateway.yaml` or `gateway.yml`. The repo root's `gateway.yaml` is the single
source of truth for both the plugin selection and everything the plugin needs
— models, workspace, and sandbox:

```yaml
agent:
  plugin: cara
  config:
    models:
      - gpt-5.3-codex-spark
      - gpt-5.6-sol
    workspace:
      root: ~/.cara/workspace
      max_file_bytes: null
    sandbox:
      image: cara-bash-sandbox:latest
      shell: /bin/bash
      network_access: true
      defaults:
        home: /tmp
        timeout_seconds: 15
        max_output_bytes: 1000000
      limits:
        memory_bytes: 268435456
        pids: 64
        cpus: 1
      mounts:
        cli_credentials:
          - name: spoti
            target: /tmp/.config/spoti
      reserved_targets:
        - /workspace
```

The first configured model drives the conversation initially with the
provider's default reasoning effort. The agent receives tools for inspecting
and changing its model and reasoning effort at runtime. A candidate
configuration must pass a separate model smoke test before it becomes active;
if validation fails, the previous configuration remains active.

Database connectivity defaults to a local SQLite file
(`sqlite+aiosqlite:///./gateway.sqlite3`) and can be overridden via
`DATABASE_URL`.
