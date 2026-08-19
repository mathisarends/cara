import asyncio
from collections.abc import AsyncIterator
from types import SimpleNamespace

from vocalbin.piper.tts import TextToSpeech as VocalbinTextToSpeech

from voice.tts import PiperTextToSpeech


def _piper() -> PiperTextToSpeech:
    voice = SimpleNamespace(config=SimpleNamespace(sample_rate=22_050))
    return PiperTextToSpeech(voice=voice)


def test_sample_rate_comes_from_the_loaded_voice() -> None:
    assert _piper().sample_rate == 22_050


def test_synthesize_flushes_finished_sentences_while_text_streams(monkeypatch) -> None:
    synthesized: list[str] = []

    async def stream(self, text, **kwargs):
        synthesized.append(text)
        yield text.encode()

    async def deltas() -> AsyncIterator[str]:
        yield "Das Licht im Wohnzimmer ist jetzt gedimmt. "
        yield "Soll ich "
        yield "noch etwas tun?"

    monkeypatch.setattr(VocalbinTextToSpeech, "stream", stream)
    tts = _piper()

    async def run() -> list[bytes]:
        return [chunk async for chunk in tts.synthesize(deltas())]

    chunks = asyncio.run(run())
    assert synthesized == [
        "Das Licht im Wohnzimmer ist jetzt gedimmt.",
        "Soll ich noch etwas tun?",
    ]
    assert chunks == [
        b"Das Licht im Wohnzimmer ist jetzt gedimmt.",
        b"Soll ich noch etwas tun?",
    ]
