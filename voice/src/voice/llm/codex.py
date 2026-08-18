from collections.abc import AsyncIterator

from llm import CodexModel, CodexReasoningEffort, CodexSession, StreamTextDelta
from voice.llm.events import AgentEvent, TextDelta, TurnCompleted

_INSTRUCTIONS = (
    "You are Cara, a voice assistant living in this apartment. "
    "You hear through a microphone, think, and answer out loud in real time. "
    "Reply very concisely: one to two short sentences, "
    "no lists, no markdown, no filler phrases. "
    "Always respond in English. "
    "When asked to introduce yourself, be warm, confident and a little playful: "
    "give your name, say in one breath that you listen, think and speak "
    "without anyone touching a keyboard, name one or two concrete things you can do "
    "such as dimming the Hue lights or taking over the Sonos speakers, "
    "and close with a short invitation to just ask for something. "
    "Keep even that introduction to three sentences at most."
)


class CodexAgentSession:
    def __init__(self, model: CodexModel = CodexModel.SPARK) -> None:
        self._session = CodexSession(
            model,
            reasoning_effort=CodexReasoningEffort.LOW,
            instructions=_INSTRUCTIONS,
        )

    async def start_turn(self, text: str) -> AsyncIterator[AgentEvent]:
        return self._stream_turn(text)

    async def _stream_turn(self, text: str) -> AsyncIterator[AgentEvent]:
        async for event in self._session.stream(text):
            if isinstance(event, StreamTextDelta) and event.delta:
                yield TextDelta(event.delta)
        yield TurnCompleted()

    async def steer(self, text: str) -> None:
        pass

    async def interrupt(self) -> None:
        pass
