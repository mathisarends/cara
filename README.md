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
uv run --extra sonos python main.py
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

Sonos playback and discovery use the optional `sonos` dependency. Import Sonos explicitly from
`cara.audio.sonos`; importing `cara` or `cara.audio` does not load it.

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
result limit truncates it. Built-in operations are grouped into `CoreTools`, `AudioTools`, `BashTools`,
and `FileSystemTools`; additional groups implement the small `Toolset.register()` protocol.

The built-in `bash` tool is disabled by default. Callers may configure explicit command prefixes with
`Tools(bash_allowed_commands=("pwd",))`. Even then, each invocation is restricted to one
command in the workspace; redirects, pipes, substitutions, and command chaining are rejected. This
allow-list is a policy boundary, not an OS sandbox—only commands whose complete behavior is trusted
should be enabled.
