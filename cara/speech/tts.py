import inspect
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from cara.settings import OpenAICredentials
from cara.speech.models import TextToSpeechRequest, TextToSpeechResponse

CONTENT_TYPES = {
    "mp3": "audio/mpeg",
    "opus": "audio/opus",
    "aac": "audio/aac",
    "flac": "audio/flac",
    "wav": "audio/wav",
    "pcm": "audio/pcm",
}


class AsyncOpenAITextToSpeech:
    """Small wrapper around OpenAI speech generation."""

    def __init__(self, client: AsyncOpenAI | None = None, *, api_key: str | None = None) -> None:
        if client is None:
            openai_credentials = OpenAICredentials()
            client = AsyncOpenAI(api_key=api_key or openai_credentials.require_api_key())
        self.client = client

    async def synthesize(self, request: TextToSpeechRequest) -> TextToSpeechResponse:
        result = await self.client.audio.speech.create(**request.to_openai_params())
        audio = await _read_audio_bytes(result)

        return TextToSpeechResponse(
            audio=audio,
            model=request.model,
            voice=request.voice,
            response_format=request.response_format,
            content_type=CONTENT_TYPES[request.response_format],
        )

    async def synthesize_to_file(self, request: TextToSpeechRequest, output_path: str | Path) -> Path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        response = await self.synthesize(request)
        output.write_bytes(response.audio)
        return output


async def text_to_speech(request: TextToSpeechRequest, client: Any | None = None) -> TextToSpeechResponse:
    return await AsyncOpenAITextToSpeech(client=client).synthesize(request)


async def _read_audio_bytes(result: Any) -> bytes:
    read = getattr(result, "read", None)
    if callable(read):
        data = read()
        if inspect.isawaitable(data):
            data = await data
        if isinstance(data, bytes):
            return data

    content = getattr(result, "content", None)
    if isinstance(content, bytes):
        return content

    if isinstance(result, bytes):
        return result

    raise TypeError("OpenAI speech response did not expose audio bytes")
