from uuid import UUID

from cara_agent_plugin_api import (
    AgentAssistantMessage,
    AgentContext,
    AgentContextEntry,
    AgentSessionReader,
    AgentToolCall,
    AgentToolCallSequence,
    AgentToolCallState,
    AgentUserMessage,
)
from gateway.features.conversation.domain import (
    AssistantMessage,
    SessionEntry,
    SessionNotFoundError,
    SessionRepository,
    ToolCall,
    ToolCallSequence,
    ToolCallState,
    UserMessage,
)


class GatewayAgentSessionReader(AgentSessionReader):
    def __init__(self, sessions: SessionRepository) -> None:
        self._sessions = sessions

    async def context_for_turn(
        self,
        session_id: UUID,
        input_id: UUID,
    ) -> AgentContext:
        session = await self._sessions.find_by_id(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)

        entries: list[AgentContextEntry] = []
        for entry in session.entries:
            if entry.id == input_id:
                return AgentContext(tuple(entries), session.metadata)
            entries.append(_context_entry(entry))
        raise ValueError(f"Input {input_id} does not belong to session {session_id}")


def _context_entry(entry: SessionEntry) -> AgentContextEntry:
    if isinstance(entry, UserMessage):
        return AgentUserMessage(entry.id, entry.content)
    if isinstance(entry, AssistantMessage):
        return AgentAssistantMessage(entry.id, entry.content)
    if isinstance(entry, ToolCallSequence):
        return AgentToolCallSequence(
            id=entry.id,
            calls=tuple(_tool_call(call) for call in entry.calls),
        )
    raise TypeError(f"Unsupported session entry: {type(entry).__name__}")


def _tool_call(call: ToolCall) -> AgentToolCall:
    if call.state is ToolCallState.PENDING:
        raise ValueError(f"Tool call {call.call_id} is still pending")
    return AgentToolCall(
        id=call.id,
        call_id=call.call_id,
        name=call.function_name,
        arguments=call.function_arguments,
        state=AgentToolCallState(call.state.value),
        result=call.result,
        error=call.error,
    )
