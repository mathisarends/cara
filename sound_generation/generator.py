from __future__ import annotations

from typing import TYPE_CHECKING

from sound_generation.ports import SoundGenerator
from sound_generation.settings import ElevenLabsCredentials
from sound_generation.views import SoundEffectRequest, SoundEffectResponse

if TYPE_CHECKING:
    from elevenlabs.client import AsyncElevenLabs


class ElevenLabsSoundGenerator(SoundGenerator):
    def __init__(self, api_key: str | None = None) -> None:
        credentials = ElevenLabsCredentials()
        self._client = _load_async_client()(api_key=api_key or credentials.api_key.get_secret_value())

    async def generate(self, request: SoundEffectRequest) -> SoundEffectResponse:
        stream = self._client.text_to_sound_effects.convert(
            text=request.text,
            model_id=request.model,
            output_format=request.output_format,
            duration_seconds=request.duration_seconds,
            prompt_influence=request.prompt_influence,
            loop=request.loop,
        )
        audio = b"".join([chunk async for chunk in stream])
        return SoundEffectResponse.from_request(request, audio)


def _load_async_client() -> type[AsyncElevenLabs]:
    try:
        from elevenlabs.client import AsyncElevenLabs
    except ModuleNotFoundError as exc:
        raise RuntimeError("Sound generation requires the optional dependency group: `cara[elevenlabs]`.") from exc
    return AsyncElevenLabs
