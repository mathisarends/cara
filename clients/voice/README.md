# voice

Cara's device-side voice session. It owns the microphone, speaker, wake word,
audio buffering, acoustic echo cancellation, barge-in detection, and local
device integrations. The Gateway owns the voice session, STT, conversation
turn, TTS, and persisted turn state.

The local session therefore needs no Deepgram SDK or provider credentials. It uses
three Gateway transports:

- REST opens or resumes a voice session and loads its snapshot.
- JSON-RPC starts and interrupts turns and streams typed lifecycle events.
- The generated bidirectional `voice.media` stream uploads microphone PCM and
  receives assistant PCM.

## Pipeline

```text
microphone -> echo cancellation -> ring buffer -> Gateway media input
                     |                              |
              wake word / VAD                Gateway STT + agent + TTS
                     |                              |
speaker <- AudioBridge <- Gateway media output + voice/conversation events
```

`GatewayVoiceSession.connect()` subscribes before loading the REST snapshot.
Persisted voice events already represented by that snapshot are filtered using
`last_sequence`; transient transcript partials remain live. An active turn from
the snapshot is restored when the channel starts.

Barge-in stops local playback immediately, interrupts the authoritative
Gateway turn, and starts a new turn from the retained microphone pre-roll.

After assistant playback, the Gateway starts the follow-up turn and owns its
inactivity countdown. The client only streams microphone audio and reacts to
`voice.conversation.*` events; conversation end drives its sleep earcon,
lighting state, and audio-focus release.

## Wiring

```python
from voice import VoiceSessionFactory

factory = VoiceSessionFactory.from_yaml()
session = await factory.create()
async with session:
    await session.run()
```

`VoiceSessionFactory.from_yaml()` loads `voice.yml` by default and also accepts
the older `voice.yaml` filename. Unknown keys, invalid values, and malformed
YAML fail immediately with the configuration path and actionable validation
details. Connection and session values can be overridden with environment
variables such as `CARA_GATEWAY_TOKEN` and `CARA_ROOM`.

The `room` must remain stable for a voice client so it can resume its open voice
session after reconnecting and receive reminders created there. Set
`new_session: true` to close any open voice session for that room and create a
fresh conversation session.

Scheduled Gateway output arrives as a proactive turn: the client does not open
its microphone or need an `ExternalActivationSource`; it simply plays the
Gateway's streamed response for its configured room.

## Reading the log

At `INFO` the `voice` logger narrates one turn from both ends of the Gateway
connection: every voice event the client accepts or drops (`voice.gateway.session`),
every turn it starts and ends, and every activation it has to ignore because the
previous turn never ended (`voice.gateway.bridge`). A turn that stalls is the gap
between the last accepted event and the missing `Voice turn ... ended`.

That is enough to locate a stalled turn. `DEBUG` only adds the `EventTrace`
listener, which logs every event on the bus in the order it was emitted, with
streamed chunks counted rather than logged. Raise the level on the `voice`
logger alone, as the example scripts do via `CARA_VOICE_LOG_LEVEL`; a `DEBUG`
root level makes `websockets` log every media frame:

```python
logging.basicConfig(level=logging.INFO)
logging.getLogger("voice").setLevel(logging.DEBUG)
```

## Local extension points

| Port | Implementations |
| --- | --- |
| `AudioInput` / `AudioOutput` | `MicrophoneAudioInput`; `LocalAudioOutput`, `SonosOutput` |
| `VoiceActivityDetector` | `SileroVoiceActivityDetector` |
| `BargeInStrategy` | `WakeWordBargeIn`, `SpeechBargeIn`, `NoBargeIn` |
| `ActivationSource` | `WakeWordActivationSource`, `ExternalActivationSource` |
| `VoiceIntegration` | earcons, Hue lighting and Sonos audio focus |

Conversation audio recording remains local. Provider selection and
`CARA_GATEWAY_VOICE_DEEPGRAM_API_KEY` belong to the Gateway configuration.
