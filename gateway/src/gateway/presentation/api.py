import asyncio
from contextlib import suppress
from typing import Any

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from gateway.application import (
    EventBroker,
    EventReceiver,
    GatewayEvent,
    GatewayService,
    RunNotFoundError,
    SessionNotFoundError,
)
from gateway.presentation.protocol import (
    ChatSendCommand,
    CommandType,
    ErrorResponse,
    EventEnvelope,
    RunCancelCommand,
    SessionCreateCommand,
    SessionCreateRequest,
    SessionGetCommand,
    SessionResponse,
    command_adapter,
)

router = APIRouter()


@router.post(
    "/sessions",
    operation_id="create_session",
    response_model=SessionResponse,
    response_description="The newly created session.",
    status_code=201,
    summary="Create a session",
    tags=["sessions"],
)
@inject
async def create_session(
    request: SessionCreateRequest,
    service: FromDishka[GatewayService],
) -> SessionResponse:
    session = await service.create_session(request.metadata)
    return SessionResponse.from_session(session)


@router.get(
    "/sessions/{session_id}",
    operation_id="get_session",
    response_model=SessionResponse,
    response_description="The requested session.",
    responses={404: {"model": ErrorResponse, "description": "Session not found."}},
    summary="Get a session",
    tags=["sessions"],
)
@inject
async def get_session(
    session_id: str,
    service: FromDishka[GatewayService],
) -> SessionResponse:
    try:
        session = await service.get_session(session_id)
    except SessionNotFoundError as error:
        raise HTTPException(status_code=404, detail="Session not found") from error
    return SessionResponse.from_session(session)


@router.websocket("/ws/{client_id}", name="gateway_event_stream")
@inject
async def gateway_socket(
    websocket: WebSocket,
    client_id: str,
    service: FromDishka[GatewayService],
    broker: FromDishka[EventBroker],
) -> None:
    await websocket.accept()
    queue = broker.connect(client_id)
    sender = asyncio.create_task(_send_events(websocket, queue))
    try:
        while True:
            raw_command = await websocket.receive_json()
            try:
                command = command_adapter.validate_python(raw_command)
                await _handle_command(client_id, command, service, broker)
            except ValidationError as error:
                await _reject(
                    broker,
                    client_id,
                    raw_command,
                    "invalid_command",
                    str(error),
                )
            except SessionNotFoundError:
                await _reject(
                    broker,
                    client_id,
                    raw_command,
                    "session_not_found",
                    "Session not found",
                )
            except RunNotFoundError:
                await _reject(
                    broker,
                    client_id,
                    raw_command,
                    "run_not_found",
                    "Run not found in this session",
                )
    except WebSocketDisconnect:
        pass
    finally:
        broker.disconnect(client_id)
        sender.cancel()
        with suppress(asyncio.CancelledError):
            await sender


async def _handle_command(
    client_id: str,
    command: SessionCreateCommand
    | SessionGetCommand
    | ChatSendCommand
    | RunCancelCommand,
    service: GatewayService,
    broker: EventBroker,
) -> None:
    if isinstance(command, SessionCreateCommand):
        session = await service.create_session(command.payload.metadata)
        broker.subscribe(client_id, session.id)
        await _accepted(broker, client_id, command.request_id, command.type, session.id)
        await broker.publish(
            GatewayEvent(
                type="session.created",
                session_id=session.id,
                request_id=command.request_id,
                data=SessionResponse.from_session(session).model_dump(mode="json"),
            )
        )
        return

    session = await service.get_session(command.session_id)
    broker.subscribe(client_id, session.id)

    if isinstance(command, SessionGetCommand):
        await _accepted(broker, client_id, command.request_id, command.type, session.id)
        await broker.publish_to(
            client_id,
            GatewayEvent(
                type="session.snapshot",
                session_id=session.id,
                request_id=command.request_id,
                data=SessionResponse.from_session(session).model_dump(mode="json"),
            ),
        )
        return

    if isinstance(command, ChatSendCommand):
        run = await service.prepare_run(session.id)
        await _accepted(
            broker,
            client_id,
            command.request_id,
            command.type,
            session.id,
            run_id=run.id,
        )
        service.start_run(run, command.payload.text, command.payload.metadata)
        return

    run = await service.cancel_run(session.id, command.payload.run_id)
    await _accepted(
        broker,
        client_id,
        command.request_id,
        command.type,
        session.id,
        run_id=run.id,
    )


async def _accepted(
    broker: EventBroker,
    client_id: str,
    request_id: str,
    command_type: CommandType,
    session_id: str,
    *,
    run_id: str | None = None,
) -> None:
    await broker.publish_to(
        client_id,
        GatewayEvent(
            type="command.accepted",
            session_id=session_id,
            run_id=run_id,
            request_id=request_id,
            data={"command": command_type.value},
        ),
    )


async def _reject(
    broker: EventBroker,
    client_id: str,
    raw_command: Any,
    code: str,
    message: str,
) -> None:
    command = raw_command if isinstance(raw_command, dict) else {}
    await broker.publish_to(
        client_id,
        GatewayEvent(
            type="command.rejected",
            session_id=command.get("session_id"),
            request_id=command.get("request_id"),
            data={"code": code, "message": message},
        ),
    )


async def _send_events(
    websocket: WebSocket,
    receiver: EventReceiver,
) -> None:
    while True:
        event = await receiver.receive()
        envelope = EventEnvelope.from_event(event)
        await websocket.send_json(envelope.model_dump(mode="json", exclude_none=True))
