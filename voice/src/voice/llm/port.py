from collections.abc import AsyncIterator
from typing import Protocol

from voice.llm.events import AgentEvent


class AgentSession(Protocol):
    async def start_turn(self, text: str) -> AsyncIterator[AgentEvent]: ...

    async def steer(self, text: str) -> None: ...

    async def interrupt(self) -> None: ...
