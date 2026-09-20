import asyncio
from collections.abc import AsyncGenerator, AsyncIterable, AsyncIterator
from contextlib import suppress
from types import TracebackType
from typing import Any, Self

import httpx2
from deepgram import AsyncDeepgramClient
from deepgram.extensions.types.sockets import SpeakV1ControlMessage, SpeakV1TextMessage
from deepgram.speak.v1.socket_client import AsyncV1SocketClient

from tts.deepgram.credentials import Credentials
from tts.deepgram.models import AudioEncoding, TextToSpeechConfig, TextToSpeechModel
from tts.ports import StreamingTextToSpeech

_MAX_TEXT_LENGTH = 2000


class TextToSpeechError(RuntimeError):
    def __init__(self, message: str, *, error_code: str | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code


class TextToSpeech(StreamingTextToSpeech[TextToSpeechConfig]):
    def __init__(
        self,
        api_key: str | None = None,
        *,
        client: AsyncDeepgramClient | None = None,
        model: TextToSpeechModel | str = TextToSpeechModel.AURA_2_THALIA_EN,
        encoding: AudioEncoding = AudioEncoding.LINEAR16,
        sample_rate: int | None = 24000,
    ) -> None:
        if api_key is not None and client is not None:
            raise ValueError("Pass either 'api_key' or 'client', not both.")
        # The SDK exposes no close(); owning the transport keeps teardown explicit.
        self._http_client: httpx2.AsyncClient | None = None
        if client is not None:
            self._deepgram_client = client
        else:
            resolved_api_key = _resolve_api_key(api_key)
            self._http_client = httpx2.AsyncClient(timeout=60.0, follow_redirects=True)
            self._deepgram_client = AsyncDeepgramClient(
                api_key=resolved_api_key, httpx_client=self._http_client
            )
        self._default_config = TextToSpeechConfig(
            model=model, encoding=encoding, sample_rate=sample_rate
        )

    async def aclose(self) -> None:
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def stream(
        self, text: str, *, config: TextToSpeechConfig | None = None
    ) -> AsyncGenerator[bytes]:
        validated_text = _require_valid_text(text)

        async def text_chunks() -> AsyncIterator[str]:
            yield validated_text

        audio_stream = self.stream_incremental(text_chunks(), config=config)
        try:
            async for audio in audio_stream:
                yield audio
        finally:
            await audio_stream.aclose()

    async def stream_incremental(
        self,
        text: AsyncIterable[str],
        *,
        config: TextToSpeechConfig | None = None,
    ) -> AsyncGenerator[bytes]:
        resolved_config = config if config is not None else self._default_config
        async with self._deepgram_client.speak.v1.connect(
            **_connect_params(resolved_config)
        ) as connection:
            sender = asyncio.create_task(self._send_text(connection, text))
            responses = connection.__aiter__()
            receiver = asyncio.ensure_future(anext(responses))
            sender_pending = True

            try:
                while True:
                    pending = {receiver}
                    if sender_pending:
                        pending.add(sender)
                    done, _ = await asyncio.wait(
                        pending, return_when=asyncio.FIRST_COMPLETED
                    )

                    if sender in done:
                        sender_pending = False
                        sender.result()

                    if receiver not in done:
                        continue
                    try:
                        message = receiver.result()
                    except StopAsyncIteration:
                        break

                    if isinstance(message, bytes):
                        yield message
                    elif message.type == "Warning":
                        raise TextToSpeechError(
                            message.warn_msg, error_code=message.warn_code
                        )
                    elif message.type == "Flushed":
                        break

                    receiver = asyncio.ensure_future(anext(responses))
            finally:
                await _stop_task(receiver)
                await _stop_task(sender)

    async def _send_text(
        self, connection: AsyncV1SocketClient, text: AsyncIterable[str]
    ) -> None:
        sent_text = False
        async for chunk in text:
            if not chunk:
                continue
            text_message = SpeakV1TextMessage(type="Speak", text=chunk)
            await connection.send_text(text_message)
            sent_text = True
        if not sent_text:
            raise ValueError(
                "The text stream must contain at least one non-empty chunk."
            )
        flush_message = SpeakV1ControlMessage(type="Flush")
        await connection.send_control(flush_message)


def _resolve_api_key(api_key: str | None) -> str:
    if api_key is not None:
        return api_key
    credentials = Credentials()
    return credentials.api_key.get_secret_value()


def _connect_params(config: TextToSpeechConfig) -> dict[str, str]:
    # Deepgram sends every websocket option as a query string parameter.
    params = config.model_dump(exclude_none=True, mode="json")
    return {key: str(value) for key, value in params.items()}


async def _stop_task(task: asyncio.Future[Any]) -> None:
    if not task.done():
        task.cancel()
    with suppress(Exception, asyncio.CancelledError):
        await task


def _require_valid_text(text: str) -> str:
    if not text.strip():
        raise ValueError("text must not be blank")
    if len(text) > _MAX_TEXT_LENGTH:
        raise ValueError(f"text must not exceed {_MAX_TEXT_LENGTH} characters")
    return text
