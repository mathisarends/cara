# Agent Runtime Architecture Vision

Status: target architecture and implementation guideline.

## Goals

- Keep the agent runtime and tool-calling loop inside the Gateway.
- Allow user-provided tools without loading user Python code into the Gateway.
- Run shell and workspace operations outside the Gateway process.
- Optimize for a fast, single-user, self-hosted deployment.

## Target architecture

```text
Clients
   |
   v
Gateway
|- conversation lifecycle and persistence
|- agent runtime and tool-calling loop
|- tool registry
|  |- trusted Gateway tools
|  |- Sandbox tool adapter
|  `- MCP tool providers
`- SandboxClient
       |
       | HTTP; streaming connection for process output
       v
Sandbox Manager
|- workspace -> sandbox mapping
|- lifecycle, TTL and process control
`- Docker API
       |
       v
Workspace Sandbox
|- shell processes
|- filesystem operations
|- persistent workspace volume
`- persistent CLI configuration volume
```

The Gateway must not mount the Docker socket. Only the narrowly scoped Sandbox
Manager may access the Docker API. Agent code and tools never receive Docker
access directly.

## Runtime ownership

The current `cara.agent_plugins` contract replaces the complete `AgentRunner`
and executes installed Python code with Gateway privileges. This contract is to
be removed. The Gateway owns:

- model interaction and the agentic loop;
- context assembly, steering and cancellation;
- tool-call event generation and persistence;
- composition of the effective tool catalog.

Model and tool implementations depend on typed ports. They do not replace the
runtime itself.

## Tool boundaries

Tools fall into three categories:

1. Trusted Gateway tools operate on Gateway-owned application capabilities,
   such as reminders or model selection.
2. Sandbox tools provide shell, filesystem and process operations through the
   `SandboxClient`.
3. User and integration tools run out of process and are connected through MCP.

MCP is the extension protocol, not the sandbox control protocol. The latter
needs application-specific lifecycle, workspace, streaming, cancellation and
resource-limit semantics.

The tool registry must reject duplicate names or apply an explicit configured
namespace. MCP schemas are loaded on connection and cached; they are not fetched
again for every model step.

## Sandbox scope and lifecycle

Cara is initially a single-user system. There is one sandbox per workspace, not
one sandbox per conversation session. Sessions using the same workspace share:

- files;
- installed workspace state;
- running processes and development servers;
- process state exposed by those running processes.

This sharing is intentional. The manager maintains an idempotent mapping:

```text
workspace_id -> sandbox_id
```

`ensure(workspace_id)` is single-flight: concurrent callers result in at most
one container creation.

The lifecycle is:

```text
ABSENT -> PREPARING -> READY -> IDLE -> STOPPING -> ABSENT
```

- Creating or activating a workspace schedules asynchronous sandbox prewarming.
- `turn.prepare` prewarms the model and sandbox concurrently.
- `turn.start` must not wait for the sandbox before starting model output.
- A sandbox tool call awaits `ensure(workspace_id)` if prewarming is incomplete.
- Relevant activity refreshes a configurable idle TTL.
- The manager never removes a sandbox during an active operation.
- When the TTL expires, the container and its processes are removed; the
  persistent workspace remains.
- The next operation transparently creates a new sandbox.
- Manager startup reconciles or removes containers identified by owned Docker
  labels.

Whether background processes refresh the idle TTL is still a policy decision.
A hard maximum lifetime may prevent forgotten processes from keeping a sandbox
forever.

## Performance requirements

- Container images are built or pulled during deployment, never during a turn.
- Sandbox prewarming is asynchronous and removed from the time-to-first-token
  path.
- The Gateway starts model streaming while the sandbox warms in parallel.
- The manager uses a persistent Docker API connection instead of spawning a
  Docker CLI process for every operation.
- Command output is streamed over one long-lived request; it is not polled.
- Filesystem endpoints are coarse-grained (`read`, `write`, `list`, `grep`,
  `apply_patch`) to avoid chatty remote filesystem access.
- Cold start duration, warm command latency, first-token latency and TTL reuse
  are measured in integration tests before setting concrete latency budgets.

## Sandbox API shape

The exact wire format is versioned, but the application-facing port should be
similar to:

```python
class SandboxClient(Protocol):
    async def ensure(self, workspace_id: str) -> SandboxRef: ...
    async def exec(self, workspace_id: str, request: ExecRequest) -> ExecStream: ...
    async def cancel(self, workspace_id: str, process_id: str) -> None: ...
    async def read_file(self, workspace_id: str, path: str) -> str: ...
    async def write_file(self, workspace_id: str, path: str, content: str) -> None: ...
    async def stop(self, workspace_id: str) -> None: ...
```

Requests use argument arrays where possible, explicit working directories,
bounded output, deadlines and stable operation IDs. The manager validates every
workspace and mount mapping; callers cannot supply arbitrary host mount paths.

## Deployment

Compose starts the long-lived services:

- Gateway;
- Sandbox Manager;
- configured MCP tool servers.

The Sandbox Manager dynamically creates workspace sandbox containers. Compose
does not model one service per runtime sandbox. Gateway-to-manager traffic stays
on a private network and is authenticated even in the single-user deployment.

The Docker socket is a privileged host boundary. The Sandbox Manager must stay
small, expose only the required operations, use owned labels and enforce fixed
images, mounts, networks and resource limits.

Single-user CLI credentials live in the manager-owned `cara-cli-config` volume,
mounted read-write at `/tmp/.config` in every workspace sandbox. The Gateway
never mounts this volume. Existing host credentials require an explicit one-time
import instead of arbitrary host path mounts.

Model-provider credentials are separate: the Codex model client runs inside
the Gateway and reads `/root/.codex/auth.json`. Compose bind-mounts the host
Codex home there read-only; `CARA_CODEX_HOME` overrides its source path. This
credential is never exposed to sandbox processes.

## Migration direction

1. Introduce Gateway-owned runtime and tool ports while retaining current
   behavior.
2. Move the existing agent loop behind those ports into the Gateway package.
3. Replace local `DockerSandbox` and `LocalWorkspace` dependencies with a
   `SandboxClient` adapter.
4. Add the Sandbox Manager and workspace-scoped lifecycle.
5. Add MCP providers to the Gateway tool registry.
6. Move remaining trusted tools into Gateway composition.
7. Remove `agent_plugin_api`, Python entry-point loading and the bundled agent
   plugin.

## Non-goals

- Multi-user or hostile-tenant isolation.
- Loading arbitrary Python plugins into the Gateway.
- Giving agents or MCP servers Docker access.
- Using Docker-in-Docker.
- Using MCP as the container lifecycle or process-control protocol.
