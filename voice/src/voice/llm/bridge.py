import asyncio
import logging
import random

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
from voice.events.models import VoiceTurnEnded, VoiceTurnStarted
from voice.llm.events import TextDelta, ToolCompleted, ToolStarted, TurnCompleted
from voice.llm.port import AgentSession

logger = logging.getLogger(__name__)

_TOOL_CALL_ACK_PHRASES = (
    "On it.",
    "Let me check.",
    "One sec.",
    "Give me a moment.",
    "Sure, checking now.",
)


class AgentBridge:
    """Translates an agent session stream into realtime voice events."""

    def __init__(self, *, event_bus: EventBus, session: AgentSession) -> None:
        self._event_bus = event_bus
        self._session = session
        self._preparation: asyncio.Task[None] | None = None
        self._last_ack_phrase: str | None = None

        event_bus.on(VoiceTurnStarted, self._on_turn_started)
        event_bus.on(VoiceTurnEnded, self._on_turn_ended)
        event_bus.on_request(AssistantResponseRequested, self._on_response_requested)

    async def _on_turn_started(self, _: VoiceTurnStarted) -> None:
        self._preparation = asyncio.create_task(
            self._session.prepare_turn(),
            name="voice-channel-prepare-turn",
        )

    async def _on_turn_ended(self, _: VoiceTurnEnded) -> None:
        preparation, self._preparation = self._preparation, None
        try:
            if preparation is not None:
                await preparation
        finally:
            await self._session.finish_turn()

    async def _on_response_requested(self, event: AssistantResponseRequested) -> None:
        logger.info("LLM input: %s", event.text)
        if self._preparation is not None:
            await self._preparation
        await self._event_bus.dispatch(AssistantResponseStarted(turn_id=event.turn_id))
        chunks: list[str] = []
        has_spoken_text = False
        ack_spoken = False
        try:
            events = await self._session.start_turn(event.text)
            async for agent_event in events:
                match agent_event:
                    case TextDelta(text=text) if text:
                        chunks.append(text)
                        has_spoken_text = has_spoken_text or bool(text.strip())
                        await self._event_bus.dispatch(
                            AssistantTextChunk(
                                turn_id=event.turn_id,
                                chunk=text,
                            )
                        )
                    case ToolStarted(name=name):
                        if not has_spoken_text and not ack_spoken:
                            await self._event_bus.dispatch(
                                AssistantTextChunk(
                                    turn_id=event.turn_id,
                                    chunk=self._pick_ack_phrase(),
                                )
                            )
                            ack_spoken = True
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

        text = "".join(chunks)
        logger.info("LLM output: %s", text)
        await self._event_bus.dispatch(
            AssistantTextCompleted(
                turn_id=event.turn_id,
                text=text,
            )
        )

    def _pick_ack_phrase(self) -> str:
        choices = [
            phrase
            for phrase in _TOOL_CALL_ACK_PHRASES
            if phrase != self._last_ack_phrase
        ]
        phrase = random.choice(choices)
        self._last_ack_phrase = phrase
        return phrase
