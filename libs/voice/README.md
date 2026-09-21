# voice

Cara's device-side voice library. The Room process owns its lifecycle; Voice owns
the microphone, speaker, wake word,
audio buffering, acoustic echo cancellation, barge-in detection, and intrinsic
audio feedback. The Gateway owns the voice session, STT, conversation
turn, TTS, and persisted turn state.

The local session therefore needs no Deepgram SDK or provider credentials. It uses
three Gateway transports:

- REST opens or resumes a voice session and loads its snapshot.
- JSON-RPC starts and interrupts turns and streams typed lifecycle events.
- The generated bidirectional `voice.media` stream uploads microphone PCM and
  receives assistant PCM.

## Pipeline

```text
microphone -> echo cancellation -> BufferedAudioInput -> TurnInputUploader -> VoiceBackend
                                        |                                          |
                          wake word / speech barge-in                Gateway STT + agent + TTS
                                        |                                          |
speaker <- PlaybackController <------------------------------ backend audio + events
```

`VoiceRuntime` owns the turn state. Activation sources, backend events,
barge-in signals and playback progress all feed its single control loop;
PCM bypasses that loop through the per-turn uploader and the playback
controller. The runtime reports stable lifecycle facts (`voice.lifecycle`) to
observers such as the integrations, the log and the trace.

`VoiceBackend` is the voice-owned port to the Gateway. Its adapter in
`voice.adapters.gateway` is the only code that knows the Gateway clients: it
subscribes before loading the REST snapshot, filters persisted events already
represented by that snapshot using `last_sequence` (transient transcript
partials remain live), and maps Gateway turn indexes on media frames to turns.
An active turn from the snapshot is restored when the runtime starts.

Barge-in stops local playback immediately, interrupts the authoritative
Gateway turn, and starts a new turn from the retained microphone pre-roll.

After assistant playback, the Gateway starts the follow-up turn and owns its
inactivity countdown. The client only streams microphone audio and reacts to
`voice.conversation.*` events; conversation end drives its sleep earcon and
notifies Room-owned integrations such as lighting and audio-focus handling.

## Wiring

```python
from voice import VoiceSessionFactory

session = await VoiceSessionFactory.from_yaml()
async with session:
    await session.run()
```

`VoiceSessionFactory.from_yaml()` loads `voice.yml` by default and also accepts
the older `voice.yaml` filename. Unknown keys, invalid values, and malformed
YAML fail immediately with the configuration path and actionable validation
details. Connection and session values can be overridden with environment
variables such as `CARA_GATEWAY_TOKEN` and `CARA_ROOM`. Tests and embedders can
pass their own `backend_connector` (a `VoiceBackendConnector`) and
`audio_devices` (an `AudioDeviceFactory`) instead of the Gateway and local audio
hardware.

The `room` must remain stable for a Room process so it receives reminders created
there. Every conversation — from the wake word until it ends through inactivity —
runs in its own conversation session: the client starts with a fresh one and
closes any voice session still open for its room, and the Gateway moves the voice
session to a new conversation session whenever a conversation ends.

Scheduled Gateway output arrives as a proactive turn: the client does not open
its microphone or need an `ExternalActivationSource`; it simply plays the
Gateway's streamed response for its configured room.

## Reading the log

At `INFO` the `voice` logger narrates one turn from both ends of the Gateway
connection: every voice event the client accepts or drops
(`voice.adapters.gateway.backend`), every turn it starts and ends, and every
activation it has to ignore because a turn is still active (`voice.runtime`). A
turn that stalls is the gap between the last accepted event and the missing
`Voice turn ... ended`.

That is enough to locate a stalled turn. `DEBUG` only adds the `LifecycleTrace`
observer (`voice.lifecycle.trace`), which logs every lifecycle event in the
order the session reached it. Raise the level on the `voice` logger alone; a
`DEBUG` root level makes
`websockets` log every media frame:

```python
logging.basicConfig(level=logging.INFO)
logging.getLogger("voice").setLevel(logging.DEBUG)
```

## Local extension points

| Port | Implementations |
| --- | --- |
| `VoiceBackend` / `VoiceBackendConnector` | `GatewayVoiceBackendConnector` |
| `AudioDeviceFactory` | local PortAudio or Sonos output, chosen from `voice.yml` |
| `AudioInput` / `AudioOutput` | `MicrophoneAudioInput`; `LocalAudioOutput`, `SonosOutput` |
| `VoiceActivityDetector` | `SileroVoiceActivityDetector` |
| `BargeInStrategy` | `WakeWordBargeIn`, `SpeechBargeIn`, `NoBargeIn` |
| `ActivationSource` | `WakeWordActivationSource`, `ExternalActivationSource` |
| `VoiceIntegration` | earcons internally; Room-owned environment integrations via injection |
| `VoiceLifecycleObserver` | `LoggingObserver`, `LifecycleTrace` |

Provider selection and `CARA_GATEWAY_VOICE_DEEPGRAM_API_KEY` belong to the
Gateway configuration.
