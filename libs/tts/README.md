# tts

Streaming text-to-speech adapters.

Ported from [vocalbin](https://github.com/mathisarends/vocalbin), reduced to the
Deepgram WebSocket adapter that Cara's gateway uses.

```python
from tts.deepgram import TextToSpeech

async with TextToSpeech(api_key, model="aura-2-thalia-en") as speech:
    async for chunk in speech.stream_incremental(text_chunks):
        ...
```
