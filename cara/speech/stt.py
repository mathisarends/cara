from typing import cast

from openai import AsyncOpenAI
from openai.types.audio import TranscriptionCreateResponse

from cara.settings import OpenAICredentials
from cara.speech.models import SpeechToTextRequest, SpeechToTextResponse
from cara.speech.ports import SpeechToText

type TranscriptionResult = TranscriptionCreateResponse | str


class OpenAISpeechToText(SpeechToText):
    def __init__(self, api_key: str | None = None) -> None:
        openai_credentials = OpenAICredentials()
        self.client = AsyncOpenAI(api_key=api_key or openai_credentials.api_key.get_secret_value())

    async def transcribe(self, request: SpeechToTextRequest) -> SpeechToTextResponse:
        params = request.to_openai_params()

        if request.audio is not None:
            file = (request.filename, request.audio)
            result = cast(
                TranscriptionResult,
                await self.client.audio.transcriptions.create(file=file, **params),
            )
        else:
            assert request.audio_path is not None  # guaranteed by model validation
            with request.audio_path.open("rb") as audio_file:
                result = cast(
                    TranscriptionResult,
                    await self.client.audio.transcriptions.create(file=audio_file, **params),
                )

        text = _extract_text(result)
        return SpeechToTextResponse(
            text=text,
            model=request.model,
            response_format=request.response_format,
            raw=_serialize_result(result),
        )


def _extract_text(result: TranscriptionResult) -> str:
    if isinstance(result, str):
        return result
    return result.text


def _serialize_result(result: TranscriptionResult) -> dict[str, object] | str:
    if isinstance(result, str):
        return result
    return result.model_dump()
