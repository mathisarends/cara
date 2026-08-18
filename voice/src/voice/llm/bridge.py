import asyncio
import logging

from voice.events import (
    AssistantResponseRequested,
    AssistantResponseStarted,
    AssistantTextChunk,
    AssistantTextCompleted,
    AssistantToolCompleted,
    AssistantToolStarted,
    VoiceTurnFailed,
)
from voice.events.bus import EventBus
from voice.llm.events import TextDelta, ToolCompleted, ToolStarted, TurnCompleted
from voice.llm.port import AgentSession

logger = logging.getLogger(__name__)


class AgentBridge:
    """Translates an agent session stream into realtime voice events."""

    def __init__(self, *, event_bus: EventBus, session: AgentSession) -> None:
        self._event_bus = event_bus
        self._session = session

        event_bus.on_request(AssistantResponseRequested, self._on_response_requested)

    async def _on_response_requested(self, event: AssistantResponseRequested) -> None:
        await self._event_bus.dispatch(AssistantResponseStarted(turn_id=event.turn_id))
        chunks: list[str] = []
        try:
            events = await self._session.start_turn(event.text)
            async for agent_event in events:
                match agent_event:
                    case TextDelta(text=text) if text:
                        chunks.append(text)
                        await self._event_bus.dispatch(
                            AssistantTextChunk(
                                turn_id=event.turn_id,
                                chunk=text,
                            )
                        )
                    case ToolStarted(name=name):
                        await self._event_bus.dispatch(
                            AssistantToolStarted(
                                turn_id=event.turn_id,
                                name=name,
                            )
                        )
                    case ToolCompleted(name=name):
                        await self._event_bus.dispatch(
                            AssistantToolCompleted(
                                turn_id=event.turn_id,
                                name=name,
                            )
                        )
                    case TurnCompleted():
                        break
                    case TextDelta():
                        pass
        except asyncio.CancelledError:
            await self._session.interrupt()
            raise
        except Exception as error:
            logger.exception("Agent response failed for voice turn %d", event.turn_id)
            await self._event_bus.dispatch(
                VoiceTurnFailed(turn_id=event.turn_id, message=str(error))
            )
            return

        await self._event_bus.dispatch(
            AssistantTextCompleted(
                turn_id=event.turn_id,
                text="".join(chunks),
            )
        )
