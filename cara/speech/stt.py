from typing import Any

from cara.speech._client import resolve_openai_client
from cara.speech.models import SpeechToTextRequest, SpeechToTextResponse


class AsyncOpenAISpeechToText:
    """Small wrapper around OpenAI audio transcriptions."""

    def __init__(self, client: Any | None = None) -> None:
        self.client = resolve_openai_client(client)

    async def transcribe(self, request: SpeechToTextRequest) -> SpeechToTextResponse:
        params = request.to_openai_params()

        with request.audio_path.open("rb") as audio_file:
            result = await self.client.audio.transcriptions.create(file=audio_file, **params)

        text = _extract_text(result)
        return SpeechToTextResponse(
            text=text,
            model=request.model,
            response_format=request.response_format,
            raw=_serialize_result(result),
        )


async def transcribe_audio(request: SpeechToTextRequest, client: Any | None = None) -> SpeechToTextResponse:
    return await AsyncOpenAISpeechToText(client=client).transcribe(request)


def _extract_text(result: Any) -> str:
    if isinstance(result, str):
        return result
    text = getattr(result, "text", None)
    if isinstance(text, str):
        return text
    if isinstance(result, dict) and isinstance(result.get("text"), str):
        return result["text"]
    raise TypeError("OpenAI transcription response did not contain text")


def _serialize_result(result: Any) -> dict[str, Any] | str:
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        return result
    model_dump = getattr(result, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    return {"text": _extract_text(result)}
