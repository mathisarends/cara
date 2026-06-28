import asyncio
from pathlib import Path

from cara import (
    AsyncOpenAISpeechToText,
    AsyncOpenAITextToSpeech,
    SpeechToTextRequest,
    TextToSpeechRequest,
)


class FakeTranscriptions:
    def __init__(self) -> None:
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return {"text": "Hallo Welt"}


class FakeSpeech:
    def __init__(self) -> None:
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return FakeAudioResponse(b"audio-bytes")


class FakeAudioResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    async def read(self) -> bytes:
        return self.content


class FakeAudio:
    def __init__(self) -> None:
        self.transcriptions = FakeTranscriptions()
        self.speech = FakeSpeech()


class FakeClient:
    def __init__(self) -> None:
        self.audio = FakeAudio()


def test_transcribe_audio_uses_async_openai_shape(tmp_path: Path) -> None:
    asyncio.run(_run_transcribe_audio_test(tmp_path))


async def _run_transcribe_audio_test(tmp_path: Path) -> None:
    audio_path = tmp_path / "sample.mp3"
    audio_path.write_bytes(b"fake-audio")
    client = FakeClient()

    response = await AsyncOpenAISpeechToText(client).transcribe(
        SpeechToTextRequest(audio_path=audio_path, language="DE")
    )

    assert response.text == "Hallo Welt"
    assert response.model == "gpt-4o-transcribe"
    assert client.audio.transcriptions.kwargs["model"] == "gpt-4o-transcribe"
    assert client.audio.transcriptions.kwargs["language"] == "de"
    assert client.audio.transcriptions.kwargs["file"].name == str(audio_path)


def test_text_to_speech_uses_async_openai_shape() -> None:
    asyncio.run(_run_text_to_speech_test())


async def _run_text_to_speech_test() -> None:
    client = FakeClient()

    response = await AsyncOpenAITextToSpeech(client).synthesize(
        TextToSpeechRequest(text="Hallo", voice="marin", response_format="wav")
    )

    assert response.audio == b"audio-bytes"
    assert response.content_type == "audio/wav"
    assert client.audio.speech.kwargs == {
        "input": "Hallo",
        "model": "gpt-4o-mini-tts",
        "voice": "marin",
        "response_format": "wav",
    }
