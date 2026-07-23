# Cara

Wake-word driven local voice loop:

1. listens for the wake word
2. records one microphone utterance until silence
3. sends the WAV to OpenAI speech-to-text
4. sends the transcript to the OpenAI Responses API
5. synthesizes the answer as WAV and plays it locally

## Run

Set `OPENAI_API_KEY`, connect a microphone and speakers, then run:

```powershell
uv run python main.py
```

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

`AudioPlayer` delegates playback to a named output strategy. Register every output that should be
available at runtime and pass the player to `VoiceAssistant`:

```python
audio_player = AudioPlayer(
    WavAudioPlayer(),
    SonosAudioPlayer(),
    active_output=AudioOutput.SONOS,
)
```

The built-in `set_audio_output` tool receives this player through the tool context and can switch to
another registered output, such as `local` or `sonos`, while the assistant is running.

## Tool safety

File tools resolve every path through a `Workspace` root jail in the filesystem adapter. Absolute paths,
parent traversal, and symlinks that resolve outside that root are rejected even if a policy middleware is
missing. A middleware chain adds configurable path policies, write-size limits, result truncation, and a
shared error boundary before invoking tools.

Tool execution uses an onion-style middleware chain. The default order is
`ErrorBoundary -> ResultLimit -> custom middleware -> PathPolicy -> ContentSize -> BashPolicy -> tool`.
The order is intentional: custom tracing sees policy denials and the original response before the outer
result limit truncates it.

The built-in `bash` tool runs in a short-lived Docker container. The container has no network access,
uses a read-only root filesystem, drops Linux capabilities, and has CPU, memory, process, output, and
execution-time limits. Only the workspace is mounted read-write, so Bash commands can still modify or
delete any file inside that workspace. By default, `Tools()` uses a dedicated scratch workspace below
the system temporary directory instead of mounting the project directory and its `.env` file. Callers
can still provide an explicit trusted `Workspace` when required.

Start Docker Desktop and prepare the local sandbox image once before using the tool:

```bash
bash scripts/prepare_bash_sandbox.sh
```

From PowerShell on Windows, Git Bash can be selected explicitly to avoid the WSL `bash.exe` launcher:

```powershell
& 'C:\Program Files\Git\usr\bin\bash.exe' scripts/prepare_bash_sandbox.sh
```

The setup script explicitly pulls the Python base image, builds `cara-bash-sandbox:latest`, and verifies
Bash and Python with Docker's `--pull=never` mode. The resulting image contains Python 3.13, available as
both `python` and `python3`. It is never pulled or built automatically during a tool call. The current
temporary Bash policy permits every command because the Docker container is the security boundary.
