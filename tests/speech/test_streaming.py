import asyncio
from collections.abc import AsyncIterator

from cara.speech import TextToSpeechRequest, TextToSpeechResponse, TextToSpeechVoice
from cara.speech.streaming import PunctuationSentenceChunker, StreamingTextToSpeech


class RecordingTextToSpeech:
    def __init__(self) -> None:
        self.texts: list[str] = []
        self.second_chunk_synthesized = asyncio.Event()

    async def synthesize(self, request: TextToSpeechRequest) -> TextToSpeechResponse:
        self.texts.append(request.text)
        if len(self.texts) == 2:
            self.second_chunk_synthesized.set()
        return TextToSpeechResponse(
            audio=request.text.encode(),
            model=request.model,
            voice=request.voice,
            response_format=request.response_format,
            content_type="audio/wav",
        )


class BlockingFirstAudioPlayer:
    def __init__(self, tts: RecordingTextToSpeech) -> None:
        self._tts = tts
        self.audio: list[bytes] = []

    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        self.audio.append(audio)
        if len(self.audio) == 1:
            await asyncio.wait_for(self._tts.second_chunk_synthesized.wait(), timeout=1)


async def _text_chunks(*chunks: str) -> AsyncIterator[str]:
    for chunk in chunks:
        yield chunk


def test_punctuation_sentence_chunker_handles_token_boundaries_and_final_fragment() -> None:
    chunker = PunctuationSentenceChunker()

    assert chunker.add("Hallo Welt") == []
    assert chunker.add(". Wie") == ["Hallo Welt."]
    assert chunker.add(" geht es? ") == ["Wie geht es?"]
    assert chunker.add("Gut") == []
    assert chunker.flush() == "Gut"
    assert chunker.flush() is None


def test_streaming_tts_synthesizes_ahead_while_preserving_playback_order() -> None:
    async def run() -> tuple[RecordingTextToSpeech, BlockingFirstAudioPlayer, int]:
        tts = RecordingTextToSpeech()
        player = BlockingFirstAudioPlayer(tts)
        started = 0

        async def on_started() -> None:
            nonlocal started
            started += 1

        stream = StreamingTextToSpeech(
            tts=tts,
            player=player,
            voice=TextToSpeechVoice.MARIN,
        )
        await stream.speak(_text_chunks("Erster Satz.", "Zweiter Satz."), on_started=on_started)
        return tts, player, started

    tts, player, started = asyncio.run(run())

    assert tts.texts == ["Erster Satz.", "Zweiter Satz."]
    assert player.audio == [b"Erster Satz.", b"Zweiter Satz."]
    assert started == 1
