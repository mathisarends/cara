import asyncio
from contextlib import suppress
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from gateway.features.conversation.application import (
    ConversationService,
    EventBroker,
    EventReceiver,
)
from gateway.features.conversation.domain import (
    GatewayEvent,
    RunNotFoundError,
    Session,
    SessionNotFoundError,
)
from gateway.features.conversation.presentation.exception_mappings import (
    command_rejection,
)
from gateway.features.conversation.presentation.schemas import (
    ChatSendCommand,
    Command,
    CommandType,
    EventEnvelope,
    RunCancelCommand,
    SessionCreateCommand,
    SessionGetCommand,
    SessionResponse,
    command_adapter,
)


class CommandProcessor:
    def __init__(self, service: ConversationService, broker: EventBroker) -> None:
        self._service = service
        self._broker = broker

    async def process(self, client_id: str, raw_command: Any) -> None:
        try:
            command = command_adapter.validate_python(raw_command)
            await self._dispatch(client_id, command)
        except (ValidationError, SessionNotFoundError, RunNotFoundError) as error:
            rejection = command_rejection(error)
            await self._reject(
                client_id,
                raw_command,
                rejection.code,
                rejection.message,
            )

    async def _dispatch(self, client_id: str, command: Command) -> None:
        if isinstance(command, SessionCreateCommand):
            await self._create_session(client_id, command)
            return

        session = await self._service.get_session(command.session_id)
        self._broker.subscribe(client_id, session.id)

        if isinstance(command, SessionGetCommand):
            await self._session_snapshot(client_id, command, session)
            return
        if isinstance(command, ChatSendCommand):
            await self._start_chat(client_id, command, session.id)
            return
        await self._cancel_run(client_id, command, session.id)

    async def _create_session(
        self,
        client_id: str,
        command: SessionCreateCommand,
    ) -> None:
        session = await self._service.create_session(command.payload.metadata)
        self._broker.subscribe(client_id, session.id)
        await self._accepted(client_id, command.request_id, command.type, session.id)
        await self._broker.publish(
            GatewayEvent(
                type="session.created",
                session_id=session.id,
                request_id=command.request_id,
                data=SessionResponse.from_domain(session).model_dump(mode="json"),
            )
        )

    async def _session_snapshot(
        self,
        client_id: str,
        command: SessionGetCommand,
        session: Session,
    ) -> None:
        await self._accepted(client_id, command.request_id, command.type, session.id)
        await self._broker.publish_to(
            client_id,
            GatewayEvent(
                type="session.snapshot",
                session_id=session.id,
                request_id=command.request_id,
                data=SessionResponse.from_domain(session).model_dump(mode="json"),
            ),
        )

    async def _start_chat(
        self,
        client_id: str,
        command: ChatSendCommand,
        session_id: str,
    ) -> None:
        run = await self._service.prepare_run(session_id)
        await self._accepted(
            client_id,
            command.request_id,
            command.type,
            session_id,
            run_id=run.id,
        )
        self._service.start_run(run, command.payload.text, command.payload.metadata)

    async def _cancel_run(
        self,
        client_id: str,
        command: RunCancelCommand,
        session_id: str,
    ) -> None:
        run = await self._service.cancel_run(session_id, command.payload.run_id)
        await self._accepted(
            client_id,
            command.request_id,
            command.type,
            session_id,
            run_id=run.id,
        )

    async def _accepted(
        self,
        client_id: str,
        request_id: str,
        command_type: CommandType,
        session_id: str,
        *,
        run_id: str | None = None,
    ) -> None:
        await self._broker.publish_to(
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
        self,
        client_id: str,
        raw_command: Any,
        code: str,
        message: str,
    ) -> None:
        command = raw_command if isinstance(raw_command, dict) else {}
        await self._broker.publish_to(
            client_id,
            GatewayEvent(
                type="command.rejected",
                session_id=command.get("session_id"),
                request_id=command.get("request_id"),
                data={"code": code, "message": message},
            ),
        )


async def serve_socket(
    websocket: WebSocket,
    client_id: str,
    processor: CommandProcessor,
    broker: EventBroker,
) -> None:
    await websocket.accept()
    receiver = broker.connect(client_id)
    sender = asyncio.create_task(_send_events(websocket, receiver))
    try:
        while True:
            await processor.process(client_id, await websocket.receive_json())
    except WebSocketDisconnect:
        pass
    finally:
        broker.disconnect(client_id)
        sender.cancel()
        with suppress(asyncio.CancelledError):
            await sender


async def _send_events(websocket: WebSocket, receiver: EventReceiver) -> None:
    while True:
        event = await receiver.receive()
        envelope = EventEnvelope.from_event(event)
        await websocket.send_json(envelope.model_dump(mode="json", exclude_none=True))
