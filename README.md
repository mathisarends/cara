# Cara

Input-agnostic conversational agent with terminal and wake-word-driven voice sessions. The shared
agent handles text, conversation history, skills, and tools. Voice mode wraps it in this local audio
pipeline:

1. listens for the wake word
2. records one microphone utterance until silence
3. sends the WAV to OpenAI speech-to-text
4. sends the transcript to the OpenAI Responses API
5. synthesizes the answer as WAV and plays it locally

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

Clients connect to `ws://127.0.0.1:8000/v1/conversation`. Commands, correlated
responses, and subscribed events use one JSON-RPC 2.0 WebSocket. The wire
models and request validation are internal to the gateway's conversation
presentation layer.

Connect a microphone and speakers, then run the voice client:

```powershell
uv run python voice_main.py
```

Say **Hey Mycroft**, wait for the wake sound, and speak. Cara records until you
stop speaking, answers through the speakers, and briefly listens for a follow-up.
Press Ctrl+C to stop the client.

For a traditional text conversation in the terminal, run:

```powershell
uv run python main.py
```

Terminal input, including short replies such as `1`, `2`, or `3`, is sent to the same conversation
gateway as transcribed speech. Use `exit`, `quit`, `:q`, Ctrl+C, or EOF to leave terminal mode.

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
