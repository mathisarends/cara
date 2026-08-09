import asyncio
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

from experiments.terminal import TerminalRenderer
from gateway_client import ChatCompletedEvent, GatewayEventType
from main import GatewayTurnRunner


class _EventStream(AbstractAsyncContextManager):
    def __init__(self, events: list[ChatCompletedEvent]) -> None:
        self._events = events
        self.consumed = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def __aiter__(self):
        for event in self._events:
            self.consumed += 1
            yield event


class _Client:
    def __init__(self, stream: _EventStream) -> None:
        self._stream = stream
        self.sessions = SimpleNamespace(start_chat=self._start_chat)

    def event_stream(self, session_id: UUID) -> _EventStream:
        return self._stream

    async def _start_chat(self, session_id: UUID, request) -> None:
        return None


def _completed_event(
    session_id: UUID,
    sequence: int,
    text: str,
    finish_reason: str,
) -> ChatCompletedEvent:
    return ChatCompletedEvent.model_validate(
        {
            "type": GatewayEventType.CHAT_COMPLETED,
            "event_id": uuid4(),
            "timestamp": datetime.now(UTC),
            "session_id": session_id,
            "sequence": sequence,
            "data": {"text": text, "finish_reason": finish_reason},
        }
    )


def test_gateway_turn_runner_keeps_consuming_after_tool_call_segment() -> None:
    session_id = uuid4()
    stream = _EventStream(
        [
            _completed_event(session_id, 1, "Ich schaue nach.", "tool_calls"),
            _completed_event(session_id, 2, "Gefunden.", "stop"),
        ]
    )
    runner = GatewayTurnRunner(_Client(stream), session_id)
    renderer = TerminalRenderer(
        output_writer=lambda text: None,
        stream_writer=lambda text: None,
        color=False,
    )

    asyncio.run(runner.run_turn("Suche Cara", renderer))

    assert stream.consumed == 2
