# Cara

Input-agnostic conversational agent with terminal and wake-word-driven voice sessions. A central
gateway owns conversation state, history, and turn execution over one JSON-RPC WebSocket; terminal
and voice are both just clients of it. Voice mode wraps a client around this local audio pipeline:

1. listens for the wake word
2. records one microphone utterance (the speech-to-text provider detects end of speech)
3. streams the transcript to the gateway over JSON-RPC
4. the gateway's agent plugin answers via the OpenAI Responses API, streaming the reply back
5. synthesizes the answer as audio and plays it locally

This is a learning project built to understand, hands-on, how an agent-gateway architecture like
[OpenClaw's](https://github.com/openclaw/openclaw) actually works — several concepts here (session
keys, database-first sessions, the gateway/plugin split) are deliberately adapted from it rather
than invented from scratch. Longer term, adapters to real open-cloud backends (e.g. Hermes) are
planned; today everything runs locally against OpenAI.

## Table of contents

- [Architecture](#architecture)
- [Packages](#packages)
- [Run](#run)
- [Workspace and Docker binds](#workspace-and-docker-binds)
- [Device discovery](#device-discovery)
- [Audio outputs](#audio-outputs)
- [Tool safety](#tool-safety)

## Architecture

```text
Voice client                    CLI client
(voice/, voice_main.py)         (cli/, cara-chat)
       │                               │
       │        JSON-RPC 2.0 over WebSocket ("/v1/gateway")
       ▼                               ▼
                 gateway_client (generated, typed)
                              │
                              ▼
                    gateway (FastAPI process)
      owns sessions, turns, persistence, event fan-out
                              │
                              │ AgentRunRequest, via agent_plugin_api
                              ▼
              configured AgentRunner plugin (installed package,
                 discovered by Python entry point at startup)
                              │
                              ▼
                agent (models, tools, skills, sandbox)
```

Three ideas hold this together:

- **The gateway is the only owner of conversation state.** Sessions, turns, message history, and
  tool-call records live in the gateway's database. Clients never hold history themselves — they
  send new input against a session id and receive streamed events back. See
  [`gateway`](gateway#readme) for the session/turn lifecycle in full.
- **The wire protocol is generated from code, not hand-maintained.** RPC methods and events are
  declared once, in the gateway, via decorators; `cara-gateway-schema` renders that registry into
  an OpenRPC document (`gateway/schema/gateway.openrpc.json`), and
  [`gateway_client`](gateway_client#readme) generates a fully typed Python client from that same
  document. Changing the protocol is: change a decorated method, regenerate the schema, regenerate
  the client — never edit generated files by hand. See
  [gateway → JSON-RPC / OpenRPC schema generation](gateway#json-rpc--openrpc-schema-generation) for
  the exact mechanism.
- **The agent runtime is a plugin, not a hardwired dependency.** The gateway defines a small,
  stable contract in [`agent_plugin_api`](agent_plugin_api#readme) (a run request, a read-only
  session-context reader, a streamed event union) with zero dependency on FastAPI, the database, or
  DI. [`agent`](agent#readme) implements that contract and registers itself under the Python
  entry-point group `cara.agent_plugins`; the gateway discovers, validates, and loads whichever
  plugin `gateway.toml` names at startup, and fails fast if it's missing, mismatched, or
  misconfigured — never mid-turn. See
  [gateway → Agent plugin system](gateway#agent-plugin-system) and
  [`AGENT_PLUGIN_CONCEPT.md`](AGENT_PLUGIN_CONCEPT.md) for the design rationale.

[`voice`](voice#readme) and [`cli`](cli#readme) are both thin clients built on
[`gateway_client`](gateway_client#readme): neither talks to an LLM directly, and both get
session-per-channel reuse (`session.open`) for free from the gateway.

## Packages

| Package | What it is |
| --- | --- |
| [`gateway`](gateway#readme) | FastAPI process: JSON-RPC/WebSocket protocol, sessions, turns, persistence, agent plugin host. |
| [`agent`](agent#readme) | The tool-calling agent loop, prompt assembly, and tool catalog — the gateway's default plugin. |
| [`agent_plugin_api`](agent_plugin_api#readme) | The stable, dependency-free contract between the gateway and an agent plugin. |
| [`gateway_client`](gateway_client#readme) | Generated, fully typed Python client for the gateway's JSON-RPC API. |
| [`voice`](voice#readme) | The local audio pipeline: wake word, STT/TTS, barge-in, echo cancellation, Sonos support. |
| [`cli`](cli#readme) | Interactive terminal client (`cara-chat`) for the gateway. |
| [`llm`](llm#readme) | Cara's Codex/OpenAI Responses model configuration, used by `agent`. |
| [`retrieval`](retrieval#readme) | Provider-agnostic chunking, dense/lexical/hybrid retrieval — no dependencies in the core. |
| [`scheduler`](scheduler#readme) | A small in-memory/SQLite async scheduler, independent of agent runtimes. |

## Run

The gateway runs directly on the host; Docker is not part of its runtime. Set
`OPENAI_API_KEY`, then start it from Git Bash (or WSL/macOS/Linux):

```bash
bash scripts/start_gateway.sh
```

The gateway applies pending Alembic migrations during startup and starts on
`127.0.0.1:8000`. The equivalent explicit commands are:

```powershell
uv run cara-gateway
```

Clients connect to `ws://127.0.0.1:8000/v1/gateway`. Requests, commands,
correlated responses, and subscribed events use one JSON-RPC 2.0 WebSocket.
The connection lifecycle belongs to the gateway presentation boundary; each
feature owns its wire models and request handling. See [`gateway`](gateway#readme)
for the full protocol and session/turn lifecycle.

Connect a microphone and speakers, then run the voice client:

```powershell
uv run python voice_main.py
```

Say **Hey Mycroft**, wait for the wake sound, and speak. Cara records until you
stop speaking, answers through the speakers, and briefly listens for a follow-up.
Press Ctrl+C to stop the client. See [`voice`](voice#readme) for the full pipeline.

For a terminal conversation against the same gateway, run:

```powershell
uv run cara-chat
```

`cara-chat` reuses the current session on its channel across runs, so restarting it continues the
same conversation. Use `/quit`, `/exit`, `/q`, or Ctrl+C to leave. See [`cli`](cli#readme) for the
full command list.

## Workspace and Docker binds

Cara keeps private, persistent agent state outside the repository in
`~/.cara/workspace`. The directory is both the source for prompt files and the
root exposed to file and Bash tools. `CARA_WORKSPACE_ROOT` can override it.

The expected layout is:

```text
~/.cara/workspace/
├── AGENTS.md
├── SOUL.md
├── IDENTITY.md
├── USER.md
├── TOOLS.md
├── MEMORY.md
├── HEARTBEAT.md
├── BOOTSTRAP.md
├── BOOT.md
├── memory/
│   └── YYYY-MM-DD.md
└── skills/
```

Docker binds are configured separately; each entry ends in `ro` or `rw`:

```json5
{
  agents: {
    defaults: {
      sandbox: {
        // Disabled by default. Enable only for tools that need external APIs.
        networkAccess: false,
        docker: {
          binds: [
            "/home/mathis/music:/music:ro",
          ],
        },
      },
    },
  },
}
```

Container targets below `/workspace` remain reserved for Cara and cannot be added as binds. Treat
this file as trusted configuration: an `rw` bind gives sandbox commands write
access to that host directory. `networkAccess` controls outbound network access
for Bash sandbox commands and defaults to `false`. Restart the gateway after
changing the file.

Die mit Docker Compose gestartete SQLite-Datenbank kann lokal mit sqlite-web
angesehen werden. Eine kurze Anleitung steht in
[docs/sqlite-web.md](docs/sqlite-web.md).

## Device discovery

Helper scripts under `scripts/` find the local devices Cara talks to and print the environment variables to add to your `.env`:

```bash
# Sonos speakers -> SONOS_IP_ADDRESS (skips the runtime network scan)
bash scripts/discover_sonos.sh

# Philips Hue bridge -> HUE_BRIDGE_IP and HUE_APP_KEY
# (press the bridge's link button when prompted)
bash scripts/discover_hue.sh
```

Sonos playback and discovery are provided over the local network by the
[`sonosify`](https://pypi.org/project/sonosify/) library; no Sonos cloud credentials are needed.
Set `SONOS_SPEAKER_NAME`, or `SONOS_IP_ADDRESS` to skip discovery. Import Sonos explicitly from
`voice.audio.output.sonos`; importing `voice` or `voice.audio` does not load it.

## Audio outputs

`AudioPlayer` serializes WAV and streaming PCM playback on one audio output:

```python
audio_player = AudioPlayer(SonosOutput())
```

Outputs that can change their playback level implement `voice.audio.VolumeControl` on top of the
`AudioOutput` port, so the port itself stays free of volume concerns. Inject such an output into the
tool context and the agent gains `get_volume` and `set_volume`; without it, neither tool is
offered to the model:

```python
audio_output = SonosOutput()
tools = build_tools(injected_dependencies=(audio_output,))
```

## Tool safety

Tool registration, dependency injection, schema generation, validation, middleware, skills, workspace
access, and sandboxing come from `mm-agenttoolkit`. Cara only defines its application-specific tool
catalog. File tools use `agenttoolkit.builtins.LocalWorkspace`, whose root jail rejects parent traversal
and symlinks that resolve outside the workspace.

The built-in `bash` tool uses `agenttoolkit.builtins.DockerSandbox` with a `SandboxPolicy`: by default, the
container has no network access, uses a read-only root filesystem, drops Linux capabilities, and has CPU,
memory, process, output, and execution-time limits. The reusable tool factory defaults to a dedicated
`LocalWorkspace` rooted at `~/.cara/workspace`. Skills live below that workspace at `skills/`. No
repository directory is exposed to the sandbox; in particular, `.env`, `.git`, and the source tree stay
outside it. Other callers can
provide their own `Workspace` or `Sandbox`, or opt into additional sandbox mounts, environment variables,
and network access through `build_tools()`.

Start Docker Desktop and prepare the local sandbox image once before using the tool:

```bash
bash scripts/prepare_bash_sandbox.sh
```

From PowerShell on Windows, Git Bash can be selected explicitly to avoid the WSL `bash.exe` launcher:

```powershell
& 'C:\Program Files\Git\usr\bin\bash.exe' scripts/prepare_bash_sandbox.sh
```

The setup script builds `cara-bash-sandbox:latest`, verifies its bundled runtimes and CLIs, and scaffolds
missing CLI skills in `${CARA_WORKSPACE_ROOT:-$HOME/.cara/workspace}/skills`. Existing skills are left
untouched. Images are never pulled or built automatically during a tool call.
