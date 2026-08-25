# voice

`voice` is Cara's local audio-pipeline client: wake word detection,
recording, speech-to-text, an agent turn (over the [`gateway-server`](../gateway/server) by
default), text-to-speech, and playback, wired into one event-driven
`VoiceAgent`. It layers acoustic echo cancellation and configurable barge-in
on top, so a user can interrupt the assistant mid-response, and supports both
local playback and Sonos speakers.

Voice does **not** talk to an LLM directly — `voice.llm.GatewayAgentSession`
streams turns over the Cara Gateway's JSON-RPC WebSocket, the same protocol
[`cli`](../cli) uses. `voice.llm.EchoAgentSession` exists for tests and
examples that need a deterministic session without a running gateway.

The pipeline puts special emphasis on latency compared to the traditional
"record until silence, then transcribe, then synthesize" approach: STT and
TTS are both streamed rather than run in one shot after the fact, and
barge-in plus acoustic echo cancellation let a user interrupt the assistant
mid-sentence instead of waiting it out. Ambient side effects — currently
Philips Hue room lighting reacting to conversation state (idle, listening,
processing, speaking) — are layered on top via the `Observer` API without
touching the core pipeline.

## Table of contents

- [Pipeline overview](#pipeline-overview)
- [Module layout](#module-layout)
- [Key ports](#key-ports)
- [Activation](#activation)
- [Barge-in](#barge-in)
- [Echo cancellation](#echo-cancellation)
- [Events](#events)
- [Wiring an agent](#wiring-an-agent)

## Pipeline overview

```text
mic ──▶ echo-cancelled BufferedAudioInput ──▶ WakeWordListener
                                                    │ wake word detected
                                                    ▼
                            WakeWordActivationSource ──┐
                                                       │  (any ActivationSource)
                            ExternalActivationSource ──┤
                                                       ▼
                                          ActivationCoordinator
                                                    │ while the session is idle
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
          VoiceTurnRequested              PromptTurnRequested
                    │                               │ (no microphone,
                    ▼                               │  no STT)
    SpeechToTextBridge (STT provider                │
    owns end-of-speech detection)                   │
                    │ final transcript              │
                    ▼                               │
              CommandBridge                         │
                    │                               │
                    └───────────────┬───────────────┘
                                    ▼
                          AssistantResponseRequested
                                                    │
                                                    ▼
                                    AgentBridge → AgentSession.start_turn()
                                    (GatewayAgentSession, by default)
                                                    │ text chunks
                                                    ▼
                                    TextToSpeechBridge (TTS provider)
                                                    │ PCM chunks
                                                    ▼
                                    AudioBridge → AudioPlayer → AudioOutput
                                    (LocalAudioOutput or SonosOutput)
```

Concurrently, `BargeInHandler` watches a `BargeInStrategy` for interruption
signals while the assistant is speaking; on a signal it cancels the active
turn (cascading through `AgentSession.interrupt()` and clearing playback) and
immediately starts a new turn from the interrupting speech. After playback
completes, `FollowUpHandler` opens a short wake-word-free window for a
second turn.

## Module layout

```text
voice/src/voice/
├── agent.py                VoiceAgent: composition root, activation supervisor
├── observer.py                Observer callback interface (wake word, turn start, interruption, ...)
├── sound.py                    SoundObserver: earcon playback (wake/listening/success/error/sleep)
├── sonos.py                     SonosSettings (SONOS_* env)
├── transcription.py              Transcription + TranscriptionKind (provider-agnostic)
│
├── audio/                  physical I/O and buffering
│   ├── ports.py                AudioInput, AudioOutput
│   ├── volume.py                 VolumeControl port
│   ├── input/local.py             MicrophoneAudioInput (PortAudio)
│   ├── output/local.py             LocalAudioOutput (PortAudio, software volume)
│   ├── output/sonos.py              SonosOutput (streams PCM as a growing Sonos audio clip)
│   ├── buffered_input.py            BufferedAudioInput: ring-buffered mic frames, multiple independent readers
│   ├── user_audio.py                 UserAudioProducer: publishes UserAudioChunk events
│   ├── bridge.py                      AudioBridge: AssistantAudio* events -> physical AudioOutput
│   └── player.py                       AudioPlayer: serializes WAV/PCM playback on one output
│
├── activation/              what may start a turn
│   ├── port.py                  ActivationSource + ListenActivation / PromptActivation
│   ├── coordinator.py             ActivationCoordinator: pumps every source, gates on session state
│   ├── wake_word.py                WakeWordActivationSource (also publishes WakeWordDetected)
│   └── external.py                  ExternalActivationSource: activate() to listen, prompt() to speak
│
├── wakeword/                WakeWordListener (wakewordkit) + WakeWordSettings
├── vad/                     VoiceActivityDetector port + SileroVoiceActivityDetector
├── stt/                     SpeechToText port + Deepgram/Cartesia adapters + SpeechToTextBridge
├── tts/                     TextToSpeech port + Deepgram/Cartesia/Piper adapters + TextToSpeechBridge
│
├── llm/                     the agent-turn client
│   ├── port.py                  AgentSession protocol: prepare_turn, start_turn, finish_turn, steer, interrupt
│   ├── gateway.py                 GatewayAgentSession: talks to the Cara Gateway over gateway_client
│   ├── bridge.py                   AgentBridge: drives AgentSession from AssistantResponseRequested
│   └── mock.py                      EchoAgentSession: deterministic session for tests/examples
│
├── barge_in/                BargeInStrategy port + WakeWordBargeIn / SpeechBargeIn / NoBargeIn
├── echo_cancellation/       NLMS-based acoustic echo cancellation (see below)
│
├── handler/                 orchestration on the event bus
│   ├── turn.py                  TurnCoordinator + TurnListener
│   ├── barge_in.py                 BargeInHandler
│   ├── command.py                   CommandBridge
│   ├── follow_up.py                  FollowUpHandler / FollowUpSettings
│   └── session_lifecycle.py           SpeechResourceHandler
│
├── conversation/            ConversationHistory, audio recording/mixing for the whole session
├── events/                  EventBus (Event = fan-out, Request = exactly-one-handler), the full event catalogue
├── lights/                  optional Hue lighting integration, driven by the Observer API
└── playback/                optional Sonos audio-focus policies (ducking / pause) during assistant speech
```

## Key ports

| Port | Method(s) | Implementations |
| --- | --- | --- |
| `AudioInput` | `stream_chunks()` | `MicrophoneAudioInput` |
| `AudioOutput` | `play_chunk`, `clear_buffer`, `finish_response` | `LocalAudioOutput`, `SonosOutput` |
| `VolumeControl` | `get_volume`, `set_volume` | `LocalAudioOutput`, `SonosOutput` |
| `VoiceActivityDetector` | `speech_probability(window)` | `SileroVoiceActivityDetector` |
| `SpeechToText` | `transcribe(audio) -> AsyncIterator[Transcription]` | `DeepgramSpeechToText`, Cartesia |
| `TextToSpeech` | `synthesize(text) -> AsyncIterator[bytes]` | Deepgram, Cartesia, Piper |
| `AgentSession` | `start_turn`, `steer`, `interrupt` | `GatewayAgentSession`, `EchoAgentSession` |
| `BargeInStrategy` | `signals() -> AsyncIterator[BargeInSignal]` | `WakeWordBargeIn`, `SpeechBargeIn`, `NoBargeIn` |
| `ActivationSource` | `activations() -> AsyncIterator[Activation]` | `WakeWordActivationSource`, `ExternalActivationSource` |

Injecting a `VolumeControl`-capable `AudioOutput` into the agent's tool
context is what turns on the `get_volume`/`set_volume` tools — see the [repo
root README](../README.md#audio-outputs).

`SpeechToText` owns end-of-speech detection: `voice` does not run a separate
silence timer. With the default Deepgram provider, the provider's own
turn-detection ends the utterance and `SpeechToTextBridge` reacts to it.

## Activation

The wake word is one `ActivationSource` among several, not the agent's main
loop. `ActivationCoordinator` pumps every configured source concurrently and
starts a turn from each `Activation` while the session is idle. It returns —
ending the session — as soon as the first source's stream ends, because a
source that stops producing has lost whatever it listens on.

An activation comes in two kinds, and they differ in what the turn starts from:

| Kind | Carries | Turn starts with |
| --- | --- | --- |
| `ListenActivation` | `sequence` (`None` = live audio), `speech_start_timeout` | `UserTranscriptionRequested` — microphone, then STT |
| `PromptActivation` | `prompt` | `AssistantResponseRequested` — the agent, no STT at all |

Both share turn identity, cancellation and `VoiceTurnEnded`; only the entry
point differs, so everything from the agent onwards — streaming, TTS, playback,
barge-in, and the follow-up window — is identical. A prompt turn therefore ends
with the user able to answer without a wake word.

`ExternalActivationSource` is the out-of-band entry point for both kinds: hold
a reference to it, pass it to the agent, and trigger it from a button handler,
a scheduler, or anything else.

```python
trigger = ExternalActivationSource()
agent = VoiceAgent(agent_session=agent_session, activation_sources=(trigger,))
...
await trigger.activate()                    # listen, as a button would
await trigger.prompt("The laundry is done") # let the agent speak, unprompted
```

`VoiceTurnStarted` marks a claimed turn whatever its kind, and is what the
coordinator and `AgentBridge` gate on. `UserTurnStarted` and
`AssistantTurnStarted` stay purely semantic: a prompt turn never signals
"listening" to observers such as the Hue lighting.

See `examples/voice_activation_main.py` for a runnable version.

## Barge-in

| Strategy | Interrupts when |
| --- | --- |
| `WakeWordBargeIn` (default) | The wake word is detected again while the assistant is speaking. |
| `SpeechBargeIn` | Continuous speech on the echo-cancelled mic stream stays above `min_level_dbfs` (default -45 dBFS) and above `min_speech_probability` (default 0.6, Silero VAD) for at least `min_speech_seconds` (default 0.35s). |
| `NoBargeIn` | Never — the assistant always finishes. |

On a signal, `BargeInHandler` cancels the active turn via
`TurnCoordinator.cancel_active_turn()`, which cascades through
`AgentSession.interrupt()` and clears in-flight TTS/playback, then
immediately requests a new turn starting from the interrupting audio — the
user's interrupting speech becomes the first audio of the next turn's STT,
rather than being discarded.

## Echo cancellation

A partitioned-block, frequency-domain NLMS adaptive filter (~250ms tail) with
residual spectral suppression, applied on the *input* side so that wake word
detection, STT, and speech-based barge-in never see the assistant's own
playback as user speech:

- `ReferenceTapOutput` wraps the physical `AudioOutput`, intercepting every
  `play_chunk` to downmix/resample it into a `PlaybackTimeline` — because an
  `AudioOutput` only exposes chunk *order*, not timestamps, the timeline
  reconstructs wall-clock playback timing from that order.
- `EchoCancellingInput` wraps the physical mic; for each captured chunk it
  estimates the capture instant (correcting for scheduler jitter), reads back
  the aligned reference window from the timeline, and runs the NLMS canceller
  between near-end (mic) and far-end (speaker reference) signals.
- `wrap_with_echo_cancellation(input, output, ...)` composes both wrappers
  around a pair of raw devices in one call.

The canceller detects divergence (residual power growing relative to
near-end energy) and decays its adaptation rather than compounding the error.

## Events

Two kinds on `EventBus`:

- **`Event`** — fan-out to every listener, failures collected rather than
  raised immediately (`raise_if_failed()` surfaces them explicitly).
  Includes `WakeWordDetected`, `UserTurnStarted`/`AssistantTurnStarted`,
  `UserSpeechStarted`/`UserSpeechEnded`, `UserTranscriptionUpdated`/
  `Completed`, `AssistantTextChunk`/`Completed`, `AssistantToolStarted`/
  `Completed`, `AssistantAudioStarted`/`Chunk`/`Completed`,
  `AssistantPlaybackCompleted`, `VoiceTurnEnded`/`Interrupted`/`TimedOut`/
  `Failed`, `FollowUpCountdown`/`TimedOut`.
- **`Request`** — routed to exactly one handler, failures propagate to the
  caller. `VoiceTurnRequested`, `UserTranscriptionRequested`,
  `AssistantResponseRequested`, `AudioPlaybackRequested`.

The `Observer` interface (wake word detected, user/assistant turn started,
assistant interrupted, ...) is a simpler callback surface built on top of the
event bus for integrations that don't need the full event catalogue —
`SoundObserver` (earcons) and `HueObserver` (lighting) are both built this
way.

## Wiring an agent

```python
from voice import VoiceAgent
from voice.llm import GatewayAgentSession

agent_session = await GatewayAgentSession.connect(
    "ws://127.0.0.1:8000/v1/gateway", channel="voice",
)
async with agent_session:
    agent = VoiceAgent(agent_session=agent_session)
    await agent.start()
```

Sonos output, speech-based barge-in, and Sonos ducking during assistant
speech:

```python
from sonosify import SonosClient
from voice import SpeechBargeIn, VoiceAgent, SonosAudioFocusObserver, SonosDuckingPolicy
from voice.audio.output.sonos import SonosOutput

async with SonosClient(ip) as sonos_client:
    agent = VoiceAgent(
        agent_session=agent_session,
        audio_output=SonosOutput(client=sonos_client, settings=sonos_settings),
        barge_in=SpeechBargeIn(),
        observers=(SonosAudioFocusObserver(policy=SonosDuckingPolicy(client=sonos_client)),),
    )
    await agent.start()
```

See the [repo root README](../README.md) for running `examples/voice_main.py`,
device discovery scripts, and workspace/sandbox configuration shared with
[`agent`](../agent).
