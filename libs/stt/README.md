# stt

Streaming speech-to-text adapters.

Ported from [vocalbin](https://github.com/mathisarends/vocalbin), reduced to the
Deepgram Flux adapter that Cara's gateway uses.

```python
from stt.deepgram import SpeechToText
from stt.deepgram.events import TurnEnd

async with SpeechToText(api_key, model="flux-general-en") as listener:
    async for event in listener.stream(audio_chunks):
        if isinstance(event, TurnEnd):
            ...
```
