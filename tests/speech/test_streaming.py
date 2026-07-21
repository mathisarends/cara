import asyncio
import logging
from collections.abc import AsyncIterator

from cara.speech import TextToSpeechRequest, TextToSpeechResponse, TextToSpeechVoice
from cara.speech.streaming import NaturalPauseChunker, StreamingTextToSpeech


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


def test_natural_pause_chunker_keeps_short_answers_together() -> None:
    chunker = NaturalPauseChunker(
        min_chunk_chars=300,
        target_chunk_chars=500,
        max_chunk_chars=800,
    )
    answer = "Hallo Welt. Wie geht es dir? Mir geht es gut."

    assert chunker.add(answer) == []
    assert chunker.flush() == answer
    assert chunker.flush() is None


def test_natural_pause_chunker_groups_sentences_near_the_target_size() -> None:
    chunker = NaturalPauseChunker(
        min_chunk_chars=300,
        target_chunk_chars=500,
        max_chunk_chars=800,
    )
    first_sentence = f"{'A' * 339}."
    second_sentence = f"{'B' * 139}."
    final_sentence = f"{'C' * 319}."

    chunks = chunker.add(f"{first_sentence} {second_sentence} {final_sentence}")

    assert chunks == [f"{first_sentence} {second_sentence}"]
    assert chunker.flush() == final_sentence


def test_streaming_tts_synthesizes_ahead_while_preserving_playback_order(caplog) -> None:
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

    with caplog.at_level(logging.INFO, logger="cara.speech.streaming"):
        tts, player, started = asyncio.run(run())

    assert tts.texts == ["Erster Satz.", "Zweiter Satz."]
    assert player.audio == [b"Erster Satz.", b"Zweiter Satz."]
    assert started == 1
    assert "\x1b[92m[says] Erster Satz.\x1b[0m" in caplog.messages
    assert "\x1b[92m[says] Zweiter Satz.\x1b[0m" in caplog.messages
