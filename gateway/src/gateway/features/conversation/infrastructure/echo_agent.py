from collections.abc import AsyncIterator
from uuid import UUID

from llmify import (
    AssistantMessage as LLMAssistantMessage,
)
from llmify import (
    OpenAIResponsesStreamEnd,
    StreamEnd,
    StreamTextDelta,
)
from llmify import (
    UserMessage as LLMUserMessage,
)

from gateway.features.conversation.application import AgentRunner
from gateway.features.conversation.domain import (
    AgentOutput,
    AssistantMessage,
    ChatCompleted,
    ChatDelta,
    SessionEntry,
    SessionNotFoundError,
    SessionRepository,
    UserMessage,
)


class CodexAgentRunner(AgentRunner):
    def __init__(self, sessions: SessionRepository, llm) -> None:
        self._sessions = sessions
        self._llm = llm

    async def stream(
        self,
        session_id: UUID,
        metadata: dict[str, object],
    ) -> AsyncIterator[AgentOutput]:
        del metadata
        session = await self._sessions.find_by_id(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)

        emitted_completion = False
        event_metadata = _event_metadata()

        async for event in self._llm.stream(_session_messages(session.entries)):
            if isinstance(event, StreamTextDelta):
                if event.delta:
                    yield ChatDelta(
                        text=event.delta,
                        metadata=event_metadata,
                    )
                continue
            if isinstance(event, OpenAIResponsesStreamEnd):
                emitted_completion = True
                yield ChatCompleted(
                    text=event.completion or "",
                    finish_reason=event.stop_reason,
                    metadata=event_metadata,
                )
                continue
            if isinstance(event, StreamEnd):
                emitted_completion = True
                yield ChatCompleted(
                    text=event.completion or "",
                    finish_reason=event.stop_reason,
                    metadata=event_metadata,
                )

        if not emitted_completion:
            yield ChatCompleted(
                text="",
                metadata=event_metadata,
            )


def _session_messages(
    entries: tuple[SessionEntry, ...],
) -> list[LLMUserMessage | LLMAssistantMessage]:
    return [
        LLMUserMessage(content=entry.content)
        if isinstance(entry, UserMessage)
        else LLMAssistantMessage(content=entry.content)
        for entry in entries
        if isinstance(entry, (UserMessage, AssistantMessage))
    ]


def _event_metadata() -> dict[str, object]:
    return {"llm_provider": "gpt-5.6-terra"}
