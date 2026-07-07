from pathlib import Path

from openai import AsyncOpenAI, omit

from cara.settings import OpenAICredentials
from cara.speech.models import TextToSpeechRequest, TextToSpeechResponse

_CONTENT_TYPES = {
    "mp3": "audio/mpeg",
    "opus": "audio/opus",
    "aac": "audio/aac",
    "flac": "audio/flac",
    "wav": "audio/wav",
    "pcm": "audio/pcm",
}


class OpenAITextToSpeech:
    def __init__(self, api_key: str | None = None) -> None:
        openai_credentials = OpenAICredentials()
        self.client = AsyncOpenAI(api_key=api_key or openai_credentials.require_api_key())

    async def synthesize(self, request: TextToSpeechRequest) -> TextToSpeechResponse:
        result = await self.client.audio.speech.create(
            input=request.text,
            model=request.model,
            voice=request.voice,
            instructions=request.instructions if request.instructions is not None else omit,
            response_format=request.response_format,
            speed=request.speed if request.speed is not None else omit,
        )

        return TextToSpeechResponse(
            audio=result.content,
            model=request.model,
            voice=request.voice,
            response_format=request.response_format,
            content_type=_CONTENT_TYPES[request.response_format],
        )

    async def synthesize_to_file(self, request: TextToSpeechRequest, output_path: str | Path) -> Path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        response = await self.synthesize(request)
        output.write_bytes(response.audio)
        return output
