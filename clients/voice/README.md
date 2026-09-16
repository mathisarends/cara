# voice

Cara's device-side voice session. It owns the microphone, speaker, wake word,
audio buffering, acoustic echo cancellation, barge-in detection, and local
device integrations. The Gateway owns the voice session, STT, conversation
turn, TTS, and persisted turn state.

The local session therefore needs no Deepgram SDK or provider credentials. It uses
three Gateway transports:

- REST opens or resumes a voice session and loads its snapshot.
- JSON-RPC starts and interrupts turns and streams typed lifecycle events.
- A binary WebSocket uploads microphone PCM and receives assistant PCM.

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
variables such as `CARA_GATEWAY_TOKEN` and `CARA_SESSION_CLIENT_ID`.

The `session.client_id` must remain stable for a physical client so it can
resume its open voice session after reconnecting. Set `new_session: true` to
close any open voice session for that client and create a fresh conversation
session.

## Local extension points

| Port | Implementations |
| --- | --- |
| `AudioInput` / `AudioOutput` | `MicrophoneAudioInput`; `LocalAudioOutput`, `SonosOutput` |
| `VoiceActivityDetector` | `SileroVoiceActivityDetector` |
| `BargeInStrategy` | `WakeWordBargeIn`, `SpeechBargeIn`, `NoBargeIn` |
| `ActivationSource` | `WakeWordActivationSource`, `ExternalActivationSource` |
| `VoiceIntegration` | earcons, Hue lighting, Sonos audio focus, tool acknowledgements |

Conversation audio recording remains local. Provider selection and
`CARA_GATEWAY_VOICE_DEEPGRAM_API_KEY` belong to the Gateway configuration.
