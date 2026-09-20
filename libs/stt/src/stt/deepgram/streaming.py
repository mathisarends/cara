import asyncio
from collections.abc import AsyncGenerator, AsyncIterable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, suppress
from types import TracebackType
from typing import Any, Self

import httpx2
from deepgram import AsyncDeepgramClient
from deepgram.extensions.types.sockets import ListenV2ControlMessage
from deepgram.listen.v2.socket_client import AsyncV2SocketClient, V2SocketClientResponse

from stt.deepgram.credentials import Credentials
from stt.deepgram.events import (
    Connected,
    Event,
    TurnEagerEnd,
    TurnEnd,
    TurnEvent,
    TurnResume,
    TurnStart,
    TurnUpdate,
)
from stt.deepgram.models import (
    StreamingSpeechToTextConfig,
    StreamingSpeechToTextEncoding,
    StreamingSpeechToTextModel,
)
from stt.ports import StreamingSpeechToText

_TURN_EVENTS: dict[str, type[TurnEvent]] = {
    "StartOfTurn": TurnStart,
    "Update": TurnUpdate,
    "EagerEndOfTurn": TurnEagerEnd,
    "TurnResumed": TurnResume,
    "EndOfTurn": TurnEnd,
}


class SpeechToTextError(RuntimeError):
    def __init__(self, message: str, *, error_code: str | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code


class SpeechToText(StreamingSpeechToText[StreamingSpeechToTextConfig, Event]):
    def __init__(
        self,
        api_key: str | None = None,
        *,
        client: AsyncDeepgramClient | None = None,
        model: StreamingSpeechToTextModel
        | str = StreamingSpeechToTextModel.FLUX_GENERAL_EN,
        encoding: StreamingSpeechToTextEncoding = (
            StreamingSpeechToTextEncoding.LINEAR16
        ),
        sample_rate: int = 16000,
        keyterms: list[str] | None = None,
        eot_threshold: float | None = None,
        eager_eot_threshold: float | None = None,
        eot_timeout_ms: int | None = None,
        warmup_idle_timeout: float = 30.0,
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
        self._default_config = StreamingSpeechToTextConfig(
            model=model,
            encoding=encoding,
            sample_rate=sample_rate,
            keyterms=keyterms,
            eot_threshold=eot_threshold,
            eager_eot_threshold=eager_eot_threshold,
            eot_timeout_ms=eot_timeout_ms,
        )
        self._warmup_idle_timeout = warmup_idle_timeout
        self._warmup_lock = asyncio.Lock()
        self._warmup_expiry: asyncio.Task[None] | None = None
        self._prepared: _PreparedConnection | None = None

    async def warmup(self) -> None:
        if self._prepared is not None:
            return
        async with self._warmup_lock:
            if self._prepared is not None:
                return
            context = self._deepgram_client.listen.v2.connect(
                **_connect_params(self._default_config)
            )
            connection = await context.__aenter__()
            self._prepared = _PreparedConnection(
                context, connection, self._default_config
            )
            self._warmup_expiry = asyncio.create_task(self._expire_warmup())

    async def aclose(self) -> None:
        self._cancel_warmup_expiry()
        await self._release_prepared()
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
        self,
        audio: AsyncIterable[bytes],
        *,
        config: StreamingSpeechToTextConfig | None = None,
    ) -> AsyncGenerator[Event]:
        resolved_config = config if config is not None else self._default_config
        async with AsyncExitStack() as stack:
            connection = await self._acquire(stack, resolved_config)
            sender = asyncio.create_task(self._send_audio(connection, audio))
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
                        message: V2SocketClientResponse = receiver.result()
                    except StopAsyncIteration:
                        break

                    yield _normalize_event(message)
                    receiver = asyncio.ensure_future(anext(responses))
            finally:
                await _stop_task(receiver)
                await _stop_task(sender)

    async def _acquire(
        self, stack: AsyncExitStack, config: StreamingSpeechToTextConfig
    ) -> AsyncV2SocketClient:
        prepared = self._prepared
        if prepared is not None and prepared.matches(config):
            self._prepared = None
            self._cancel_warmup_expiry()
            stack.push_async_callback(prepared.aclose)
            return prepared.connection
        context = self._deepgram_client.listen.v2.connect(**_connect_params(config))
        return await stack.enter_async_context(context)

    async def _expire_warmup(self) -> None:
        await asyncio.sleep(self._warmup_idle_timeout)
        self._warmup_expiry = None
        await self._release_prepared()

    async def _release_prepared(self) -> None:
        prepared = self._prepared
        self._prepared = None
        if prepared is not None:
            await prepared.aclose()

    def _cancel_warmup_expiry(self) -> None:
        expiry = self._warmup_expiry
        self._warmup_expiry = None
        if expiry is not None:
            expiry.cancel()

    async def _send_audio(
        self, connection: AsyncV2SocketClient, audio: AsyncIterable[bytes]
    ) -> None:
        sent_audio = False
        async for chunk in audio:
            if not chunk:
                continue
            await connection.send_media(chunk)
            sent_audio = True
        if not sent_audio:
            raise ValueError(
                "The audio stream must contain at least one non-empty chunk."
            )
        close_message = ListenV2ControlMessage(type="CloseStream")
        await connection.send_control(close_message)


class _PreparedConnection:
    """A connection opened by warmup(), consumed by at most one stream."""

    def __init__(
        self,
        context: AbstractAsyncContextManager[AsyncV2SocketClient],
        connection: AsyncV2SocketClient,
        config: StreamingSpeechToTextConfig,
    ) -> None:
        self._context = context
        self._connection = connection
        self._config = config

    @property
    def connection(self) -> AsyncV2SocketClient:
        return self._connection

    def matches(self, config: StreamingSpeechToTextConfig) -> bool:
        return self._config == config

    async def aclose(self) -> None:
        await self._context.__aexit__(None, None, None)


def _resolve_api_key(api_key: str | None) -> str:
    if api_key is not None:
        return api_key
    credentials = Credentials()
    return credentials.api_key.get_secret_value()


def _connect_params(config: StreamingSpeechToTextConfig) -> dict[str, Any]:
    # Deepgram sends every websocket option as a query string parameter.
    params = config.model_dump(exclude_none=True, mode="json", by_alias=True)
    return {
        key: value if isinstance(value, list) else str(value)
        for key, value in params.items()
    }


async def _stop_task(task: asyncio.Future[Any]) -> None:
    if not task.done():
        task.cancel()
    with suppress(Exception, asyncio.CancelledError):
        await task


def _normalize_event(message: V2SocketClientResponse) -> Event:
    # The SDK models ignore `exclude`, so drop the wire discriminator by hand.
    payload = message.model_dump()
    payload.pop("type")
    match message.type:
        case "Connected":
            return Connected.model_validate(payload)
        case "FatalError":
            raise SpeechToTextError(payload["description"], error_code=payload["code"])
        case "TurnInfo":
            event_name = payload.pop("event")
            turn_event = _TURN_EVENTS.get(event_name)
            if turn_event is None:
                raise ValueError(f"Unsupported Deepgram STT turn event: {event_name}")
            return turn_event.model_validate(payload)
        case _:
            raise ValueError(f"Unsupported Deepgram STT message type: {message.type}")
