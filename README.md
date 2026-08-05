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

Set `OPENAI_API_KEY`, connect a microphone and speakers, then run the default voice mode:

```powershell
uv run python main.py
```

For a traditional text conversation in the terminal, run:

```powershell
uv run python main.py --mode terminal
```

Terminal input, including short replies such as `1`, `2`, or `3`, is sent to the same conversation
agent as transcribed speech. Use `/exit`, `/quit`, Ctrl+C, or EOF to leave terminal mode.

The terminal composition is also available as an explicit example:

```powershell
uv run python experiments/chat_in_terminal.py
```

## Hybrid memory experiment

The `search_memory` tool searches Markdown memory chunks in `temp/cara-memory.db`
and returns concise original excerpts grouped by source and date. Hybrid relevance
scores are used internally for ranking and an adaptive cutoff, but are not added
to the conversation. Longer lexical query terms use prefix matching so German
compounds can be found. A separate mock corpus contains one durable `MEMORY.md`
and fourteen daily notes. Seed it with an `OPENAI_API_KEY` configured in `.env`:

```bash
bash scripts/seed_database_mock_data.sh
```

The command is idempotent and caches embeddings. To target another SQLite file,
pass `--database path/to/memory.db`. Remove only the dataset-prefixed mock
documents and their cached embeddings with:

```bash
bash scripts/delete_database_mock_data.sh
```

The readable Python entry points behind the wrappers are
`scripts/seed_database_mock_data.py` and `scripts/delete_database_mock_data.py`.

The default wake word is `hey_mycroft`. Runtime recordings and TTS files are written below the system temp directory in `cara`.
While Cara is responding, say the wake word again to interrupt the response and start a new turn.

## Device discovery

Helper scripts under `scripts/` find the local devices Cara talks to and print the environment variables to add to your `.env`:

```bash
# Sonos speakers -> SONOS_IP_ADDRESS (skips the runtime network scan)
bash scripts/discover_sonos.sh

# Philips Hue bridge -> HUE_BRIDGE_IP and HUE_APP_KEY
# (press the bridge's link button when prompted)
bash scripts/discover_hue.sh
```

Sonos playback and discovery are provided by the [`sonosify`](https://pypi.org/project/sonosify/)
library. Import Sonos explicitly from `cara.audio.sonos`; importing `cara` or `cara.audio` does not
load it.

## Audio outputs

`AudioPlayer` delegates playback to a named audio sink. Register every sink that should be
available at runtime and pass the player to `SpeechOutput` and the tool context:

```python
audio_player = AudioPlayer(
    LocalAudioSink(),
    SonosAudioSink(),
    active_output=AudioOutput.SONOS,
)

speech_output = SpeechOutput(tts, audio_player, speech_settings, event_bus)
tools = build_tools(audio_player)
```

The built-in `set_audio_output` tool receives this player through the tool context and can switch to
another registered output, such as `local` or `sonos`, while the assistant is running.

## Tool safety

Tool registration, dependency injection, schema generation, validation, middleware, skills, workspace
access, and sandboxing come from `mm-agenttoolkit`. Cara only defines its application-specific tool
catalog. File tools use `agenttoolkit.builtins.LocalWorkspace`, whose root jail rejects absolute paths,
parent traversal, and symlinks that resolve outside the workspace.

The built-in `bash` tool uses `agenttoolkit.builtins.DockerSandbox` with a `SandboxPolicy`: by default, the
container has no network access, uses a read-only root filesystem, drops Linux capabilities, and has CPU,
memory, process, output, and execution-time limits. Only the workspace is mounted read-write. By default,
`Tools()` uses a dedicated `LocalWorkspace` below the system temporary directory instead of mounting the
project directory and its `.env` file. Callers can provide another `Workspace` or `Sandbox` explicitly, or
opt into additional sandbox mounts, environment variables, and network access through `build_tools()`.

Start Docker Desktop and prepare the local sandbox image once before using the tool:

```bash
bash scripts/prepare_bash_sandbox.sh
```

From PowerShell on Windows, Git Bash can be selected explicitly to avoid the WSL `bash.exe` launcher:

```powershell
& 'C:\Program Files\Git\usr\bin\bash.exe' scripts/prepare_bash_sandbox.sh
```

The setup script builds `cara-bash-sandbox:latest` and verifies its bundled runtimes and CLIs. Images are
never pulled or built automatically during a tool call.
