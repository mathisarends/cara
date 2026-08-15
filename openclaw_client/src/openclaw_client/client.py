import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from types import TracebackType
from typing import Any, Self, cast
from uuid import uuid4

from pydantic import TypeAdapter, ValidationError
from websockets.asyncio.client import ClientConnection
from websockets.asyncio.client import connect as ws_connect
from websockets.exceptions import ConnectionClosed

from openclaw_client.exceptions import (
    OpenClawClientError,
    OpenClawGatewayError,
    OpenClawNotConnectedError,
    OpenClawProtocolError,
)
from openclaw_client.models import (
    PROTOCOL_VERSION,
    ChatEvent,
    ChatSendAck,
    ErrorShape,
    EventFrame,
    GatewayAuth,
    GatewayClientInfo,
    GatewayEvent,
    HelloOk,
    OperatorScope,
    RequestFrame,
    ResponseFrame,
    SessionsCreateResult,
    TalkEvent,
)

type JsonObject = dict[str, Any]

_DEFAULT_GATEWAY_URL = "ws://127.0.0.1:18789"
_DEFAULT_REQUEST_TIMEOUT = 30.0
_DEFAULT_HANDSHAKE_TIMEOUT = 15.0
_DEFAULT_MAX_PAYLOAD = 25 * 1024 * 1024

_CHAT_EVENT_ADAPTER: TypeAdapter[ChatEvent] = TypeAdapter(ChatEvent)


class OpenClawClient:
    def __init__(
        self,
        url: str = _DEFAULT_GATEWAY_URL,
        *,
        token: str | None = None,
        password: str | None = None,
        device_token: str | None = None,
        request_timeout: float = _DEFAULT_REQUEST_TIMEOUT,
        handshake_timeout: float = _DEFAULT_HANDSHAKE_TIMEOUT,
    ) -> None:
        self._url = url
        self._auth = (
            GatewayAuth(token=token, password=password, device_token=device_token)
            if token is not None or password is not None or device_token is not None
            else None
        )
        self._request_timeout = request_timeout
        self._handshake_timeout = handshake_timeout
        self._socket: ClientConnection | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._pending: dict[str, asyncio.Future[ResponseFrame]] = {}
        self._event_queue: asyncio.Queue[EventFrame | BaseException] = asyncio.Queue()
        self._send_lock = asyncio.Lock()
        self._hello: HelloOk | None = None

    @property
    def is_connected(self) -> bool:
        return (
            self._socket is not None
            and self._hello is not None
            and self._reader_task is not None
            and not self._reader_task.done()
        )

    async def __aenter__(self) -> Self:
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()

    async def connect(self) -> HelloOk:
        if self.is_connected:
            return cast(HelloOk, self._hello)
        self._event_queue = asyncio.Queue()
        try:
            self._socket = await ws_connect(
                self._url,
                max_size=_DEFAULT_MAX_PAYLOAD,
                open_timeout=self._handshake_timeout,
            )
            self._hello = await self._perform_handshake(self._socket)
            self._reader_task = asyncio.create_task(
                self._read_frames(), name="openclaw-gateway-reader"
            )
            return self._hello
        except BaseException:
            await self.close()
            raise

    async def close(self) -> None:
        reader_task = self._reader_task
        self._reader_task = None
        if reader_task is not None and reader_task is not asyncio.current_task():
            reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reader_task
        socket = self._socket
        self._socket = None
        self._hello = None
        if socket is not None:
            await socket.close()
        self._fail_pending(OpenClawNotConnectedError("gateway connection closed"))

    async def create_session(
        self,
        *,
        key: str | None = None,
        agent_id: str | None = None,
        label: str | None = None,
        model: str | None = None,
        message: str | None = None,
    ) -> SessionsCreateResult:
        params = {
            "key": key,
            "agentId": agent_id,
            "label": label,
            "model": model,
            "message": message,
        }
        return await self._request(
            "sessions.create", params, result_model=SessionsCreateResult
        )

    async def send_message(
        self,
        *,
        session_key: str,
        message: str,
        agent_id: str | None = None,
        session_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> ChatSendAck:
        params = {
            "sessionKey": session_key,
            "message": message,
            "agentId": agent_id,
            "sessionId": session_id,
            "idempotencyKey": idempotency_key or str(uuid4()),
        }
        return await self._request("chat.send", params, result_model=ChatSendAck)

    async def events(self) -> AsyncIterator[ChatEvent | TalkEvent | GatewayEvent]:
        while True:
            item = await self._event_queue.get()
            if isinstance(item, BaseException):
                raise item
            yield _parse_event(item)

    async def _perform_handshake(self, socket: ClientConnection) -> HelloOk:
        raw_challenge = await asyncio.wait_for(
            socket.recv(), timeout=self._handshake_timeout
        )
        challenge = _parse_event_frame(raw_challenge)
        if challenge.event != "connect.challenge":
            raise OpenClawProtocolError(
                f"expected connect.challenge, received {challenge.event!r}"
            )

        request = RequestFrame(method="connect", params=_connect_params(self._auth))
        await socket.send(request.model_dump_json(by_alias=True, exclude_none=True))

        raw_response = await asyncio.wait_for(
            socket.recv(), timeout=self._handshake_timeout
        )
        response = _parse_response_frame(raw_response)
        if response.id != request.id:
            raise OpenClawProtocolError(
                "connect response id does not match the request id"
            )
        return _unwrap_result(response, HelloOk)

    async def _request[ResultT](
        self,
        method: str,
        params: JsonObject | None,
        *,
        result_model: type[ResultT],
    ) -> ResultT:
        socket = self._socket
        if socket is None or self._hello is None or self._reader_task is None:
            raise OpenClawNotConnectedError(
                "connect() must complete before sending requests"
            )
        request = RequestFrame(method=method, params=_drop_none(params))
        future: asyncio.Future[ResponseFrame] = (
            asyncio.get_running_loop().create_future()
        )
        self._pending[request.id] = future
        try:
            async with self._send_lock:
                await socket.send(
                    request.model_dump_json(by_alias=True, exclude_none=True)
                )
            response = await asyncio.wait_for(future, timeout=self._request_timeout)
        except TimeoutError as error:
            raise TimeoutError(f"gateway request {method!r} timed out") from error
        finally:
            self._pending.pop(request.id, None)
        return _unwrap_result(response, result_model)

    async def _read_frames(self) -> None:
        socket = self._socket
        assert socket is not None
        try:
            async for raw_frame in socket:
                frame = _load_gateway_frame(raw_frame)
                if isinstance(frame, ResponseFrame):
                    future = self._pending.get(frame.id)
                    if future is not None and not future.done():
                        future.set_result(frame)
                else:
                    await self._event_queue.put(frame)
        except asyncio.CancelledError:
            raise
        except ConnectionClosed as error:
            failure: BaseException = OpenClawClientError(
                f"gateway connection closed: {error}"
            )
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            failure = OpenClawProtocolError("gateway sent an invalid frame")
            failure.__cause__ = error
        except BaseException as error:
            failure = error
        else:
            failure = OpenClawClientError("gateway connection closed")
        if self._socket is socket:
            self._socket = None
            self._hello = None
        self._fail_pending(failure)

    def _fail_pending(self, error: BaseException) -> None:
        for future in tuple(self._pending.values()):
            if not future.done():
                future.set_exception(error)
        self._event_queue.put_nowait(error)


def _connect_params(auth: GatewayAuth | None) -> JsonObject:
    return {
        "minProtocol": PROTOCOL_VERSION,
        "maxProtocol": PROTOCOL_VERSION,
        "client": GatewayClientInfo().model_dump(by_alias=True, exclude_none=True),
        "role": "operator",
        "scopes": [OperatorScope.READ, OperatorScope.WRITE],
        "auth": None
        if auth is None
        else auth.model_dump(by_alias=True, exclude_none=True),
    }


def _drop_none(params: JsonObject | None) -> JsonObject | None:
    if params is None:
        return None
    return {key: value for key, value in params.items() if value is not None}


def _load_json_object(raw_frame: str | bytes) -> JsonObject:
    if isinstance(raw_frame, bytes):
        raw_frame = raw_frame.decode("utf-8")
    data = json.loads(raw_frame)
    if not isinstance(data, dict):
        raise OpenClawProtocolError("gateway frame must be a JSON object")
    return data


def _parse_event_frame(raw_frame: str | bytes) -> EventFrame:
    try:
        return EventFrame.model_validate(_load_json_object(raw_frame))
    except ValidationError as error:
        raise OpenClawProtocolError("gateway sent an invalid event frame") from error


def _parse_response_frame(raw_frame: str | bytes) -> ResponseFrame:
    try:
        return ResponseFrame.model_validate(_load_json_object(raw_frame))
    except ValidationError as error:
        raise OpenClawProtocolError("gateway sent an invalid response frame") from error


def _load_gateway_frame(raw_frame: str | bytes) -> ResponseFrame | EventFrame:
    data = _load_json_object(raw_frame)
    frame_type = data.get("type")
    try:
        if frame_type == "res":
            return ResponseFrame.model_validate(data)
        if frame_type == "event":
            return EventFrame.model_validate(data)
    except ValidationError as error:
        raise OpenClawProtocolError("gateway sent an invalid frame") from error
    raise OpenClawProtocolError(f"unexpected gateway frame type {frame_type!r}")


def _unwrap_result[ResultT](
    response: ResponseFrame, result_model: type[ResultT]
) -> ResultT:
    if not response.ok:
        error = response.error or ErrorShape(
            code="UNKNOWN", message="gateway request failed without a structured error"
        )
        raise OpenClawGatewayError(error)
    return result_model.model_validate(response.payload)  # type: ignore[attr-defined]


def _parse_event(frame: EventFrame) -> ChatEvent | TalkEvent | GatewayEvent:
    if frame.event == "chat":
        return _CHAT_EVENT_ADAPTER.validate_python(frame.payload)
    if frame.event == "talk":
        return TalkEvent.model_validate(frame.payload)
    return GatewayEvent(event=frame.event, payload=frame.payload)
