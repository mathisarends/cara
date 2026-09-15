# voice

Cara's local audio-pipeline client: wake word detection, recording,
speech-to-text, an agent turn (over [`gateway-server`](../../gateway) by
default), text-to-speech, and playback, wired into one event-driven
`VoiceChannel`. Layers acoustic echo cancellation and configurable barge-in on
top, so a user can interrupt the assistant mid-response; supports local
playback and Sonos speakers.

Voice does **not** talk to an LLM directly — `voice.llm.GatewayAgentSession`
streams turns over the Gateway's JSON-RPC WebSocket, the same protocol
[`cli`](../../clients/cli) uses. `EchoAgentSession` exists for tests/examples without a
running gateway. STT and TTS are both streamed rather than run in one shot,
and barge-in + echo cancellation let a user interrupt mid-sentence.

## Pipeline

```text
mic -> echo-cancelled input -> WakeWordListener/ExternalActivationSource
voice turn started -> Gateway turn.prepare -> ChatCodex.prewarm()
gateway session events -> GatewayAgentSession (proactive activation)
    -> ActivationCoordinator -> STT (ListenActivation) or direct (PromptActivation)
    -> AgentBridge -> AgentSession.start_turn() -> TTS -> AudioBridge -> AudioOutput
```

Concurrently, `BargeInHandler` watches for interruption signals while the
assistant speaks, cancelling the active turn and starting a new one from the
interrupting speech. `FollowUpHandler` opens a short wake-word-free window
after playback.

Echo cancellation retains the exact PCM sent to the output and acoustically
matches microphone windows against that sample history. The resulting reference
feeds an adaptive room filter. It does not depend on a configured playback
latency, so the same pipeline handles local output and buffered Sonos clips.

## Key ports

| Port | Implementations |
| --- | --- |
| `AudioInput` / `AudioOutput` | `MicrophoneAudioInput`; `LocalAudioOutput`, `SonosOutput` |
| `VoiceActivityDetector` | `SileroVoiceActivityDetector` |
| `SpeechToText` / `TextToSpeech` | Deepgram |
| `AgentSession` | `GatewayAgentSession`, `EchoAgentSession` |
| `BargeInStrategy` | `WakeWordBargeIn` (default), `SpeechBargeIn`, `NoBargeIn` |
| `ActivationSource` | `WakeWordActivationSource`, `ExternalActivationSource`, `GatewayAgentSession` |

`SpeechToText` owns end-of-speech detection — no separate silence timer.
`ExternalActivationSource` is the out-of-band entry point (`activate()` to
listen, `prompt()` to speak unprompted) for buttons, schedulers, etc.
`GatewayAgentSession` also acts as an activation source. Pass it explicitly in
`activation_sources` so that when a subscribed automation starts a turn on the
server, Voice consumes that existing event stream instead of submitting a
duplicate turn and speaks the result.

## Static tool acknowledgements

When the agent starts a tool without first speaking, Voice immediately plays a
short acknowledgement from `clients/voice/static/acknowledgements`. The WAV files are
loaded into memory when `VoiceChannel` is constructed, so this path does not
open a TTS connection at runtime.

Regenerate all acknowledgement clips with the configured `DEEPGRAM_API_KEY`:

```powershell
uv run python scripts/setup/prepare_tool_acknowledgements.py
```

The generator defaults to Deepgram's `aura-2-athena-en` voice and 24 kHz,
16-bit mono WAV output. Use `--voice`, `--sample-rate`, or `--output-dir` to
override those defaults.

## Layout

```text
clients/voice/src/voice/
├── channel.py          VoiceChannel: persistent activation channel
├── audio/                physical I/O, buffering, volume
├── activation/            what may start a turn
├── wakeword/, vad/, stt/, tts/     provider adapters + bridges
├── llm/                    AgentSession port + GatewayAgentSession/EchoAgentSession
├── barge_in/, echo_cancellation/    interruption + NLMS acoustic echo cancellation
├── handler/               event-bus orchestration (turn, barge-in, follow-up, ...)
├── conversation/, events/    history/recording, EventBus + event catalogue
└── lights/, playback/     optional Hue lighting / Sonos ducking via the Observer API
```

## Wiring

```python
agent_session = await GatewayAgentSession.connect(url, token=token, channel="voice")
async with agent_session:
    await VoiceChannel(
        agent_session=agent_session,
        activation_sources=(agent_session,),
    ).start()
```

## Dependencies

- [`gateway_rest_client`](../../generated/gateway_rest_client) and
  [`gateway_rpc_client`](../../generated/gateway_rpc_client) via `GatewayAgentSession` —
  the sole path to an LLM. `connect` resolves the session over REST, then runs
  turns over the socket.
- Injecting a `VolumeControl`-capable `AudioOutput` into `agent`'s tool
  context is what enables its volume tools — see [repo root
  README](../../README.md#audio-outputs).
